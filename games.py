"""
games.py – Módulo de juegos para Lulu Bot 🎮
Rock-Paper-Scissors y Trivia con discord.ui.View (discord.py 2.x)
"""

import json
import random
import discord
from discord.ui import View, Button
import llm
import database

# ─────────────────────────────────────────────
# Rock-Paper-Scissors (Piedra, Papel, Tijera)
# ─────────────────────────────────────────────

RPS_CHOICES = {
    "piedra": "🪨",
    "tijera": "✂️",
    "papel": "📄",
}

# resultado[jugador][lulu] → "win" | "lose" | "tie"
RPS_OUTCOMES = {
    "piedra": {"piedra": "tie", "tijera": "win", "papel": "lose"},
    "tijera": {"tijera": "tie", "papel": "win", "piedra": "lose"},
    "papel":  {"papel": "tie", "piedra": "win", "tijera": "lose"},
}

WIN_RESPONSES = [
    "JAJA te gané 💀 soy la mejor",
    "perdiste lol 😂 ni modo",
    "jajaja APLASTADA 🪦 otra?",
    "gg ez 💅 sorry not sorry",
    "JAJA qué fácil 😎 intenta de nuevo",
    "te destruí completamente 💣 no te sientas mal... bueno sí",
]

LOSE_RESPONSES = [
    "ay no, perdí 😭 eso no cuenta",
    "NOOO cómo 😤 hiciste trampa seguro",
    "ok esa no la vi venir 💀 revancha ya",
    "perdí?? PERDÍ?? imposible 😭",
    "bueno ya, te la dejo pasar ESTA VEZ 😒",
    "noooo mi racha 😢 va de nuevo",
]

TIE_RESPONSES = [
    "empate! otra vez va? 🤝",
    "jaja pensamos igual 🧠 dale otra",
    "EMPATE somos almas gemelas o qué 😳",
    "empate lol, de nuevo de nuevo 🔄",
    "igualadas jaja, va otra? 🫣",
]


class RPSView(View):
    """Vista de Piedra, Papel o Tijera."""

    def __init__(self, *, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None

    async def _handle_choice(self, interaction: discord.Interaction, player_choice: str):
        lulu_choice = random.choice(list(RPS_CHOICES.keys()))
        outcome = RPS_OUTCOMES[player_choice][lulu_choice]

        player_emoji = RPS_CHOICES[player_choice]
        lulu_emoji = RPS_CHOICES[lulu_choice]

        if outcome == "win":
            result_text = random.choice(LOSE_RESPONSES)
            color = discord.Color.green()
            title = "¡Ganaste! 😤"
            database.add_rps_win(interaction.user.id, interaction.user.name)
        elif outcome == "lose":
            result_text = random.choice(WIN_RESPONSES)
            color = discord.Color.red()
            title = "¡Perdiste! 😂"
        else:
            result_text = random.choice(TIE_RESPONSES)
            color = discord.Color.gold()
            title = "¡Empate! 🤝"

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name="Tú elegiste", value=f"{player_emoji} {player_choice.capitalize()}", inline=True)
        embed.add_field(name="Yo elegí", value=f"{lulu_emoji} {lulu_choice.capitalize()}", inline=True)
        embed.add_field(name="\u200b", value=result_text, inline=False)

        # Desactivar todos los botones
        for child in self.children:
            child.disabled = True  # type: ignore

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Piedra", emoji="🪨", style=discord.ButtonStyle.secondary)
    async def piedra_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, "piedra")

    @discord.ui.button(label="Tijera", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def tijera_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, "tijera")

    @discord.ui.button(label="Papel", emoji="📄", style=discord.ButtonStyle.secondary)
    async def papel_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, "papel")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True  # type: ignore
        embed = discord.Embed(title="⏰ Tiempo agotado", description="Nadie eligió nada, qué aburrido...", color=discord.Color.dark_grey())
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


# ─────────────────────────────────────────────
# Trivia
# ─────────────────────────────────────────────


CORRECT_RESPONSES = [
    "siii! ✨ le atinaste, eres crack",
    "BIEEEEN 🎉 sabía que la sabías (o no jaja)",
    "correctooo 💯 te la sabes te la sabes",
    "así es! 🌟 qué inteligente eres wow",
    "sí sí sí!! 🥳 respuesta correcta, toma tu estrellita ⭐",
    "omg siii 😍 eres re inteligente",
]

WRONG_RESPONSES = [
    "nel, era la {correct} jaja 💀",
    "NOOOPE 😬 la correcta era la {correct}",
    "uy no amigx 😅 era la {correct}, F",
    "mal mal mal 🚫 la respuesta era la {correct}",
    "jaja no 😂 era la {correct}… pero buen intento",
    "incorrecto bestie 💔 era la {correct}",
]

TIMEOUT_RESPONSES = [
    "muy lento 😴 se acabó el tiempo",
    "tardaste mucho!! ⏰ ya ni modo",
    "zzz 💤 te dormiste o qué",
    "se te fue el avión ✈️ ya era",
    "hello?? ⏳ bueno ya se acabó jaja",
]

OPTION_LABELS = ["A", "B", "C", "D"]
OPTION_STYLES = [
    discord.ButtonStyle.primary,
    discord.ButtonStyle.success,
    discord.ButtonStyle.secondary,
    discord.ButtonStyle.danger,
]


class TriviaView(View):
    """Vista de Trivia con 4 opciones y timeout de 15 segundos."""

    def __init__(self, question_data: dict, *, timeout: float = 15.0):
        super().__init__(timeout=timeout)
        self.question_data = question_data
        self.correct_index = question_data["answer"]
        self.answered = False
        self.message: discord.Message | None = None

        # Crear botones dinámicamente
        for i, option_text in enumerate(question_data["options"]):
            button = Button(
                label=f"{OPTION_LABELS[i]}) {option_text}",
                style=OPTION_STYLES[i],
                custom_id=f"trivia_option_{i}",
            )
            button.callback = self._make_callback(i)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if self.answered:
                await interaction.response.send_message(
                    "ya respondiste!! 😤 no seas tramposo", ephemeral=True
                )
                return

            self.answered = True
            correct_label = OPTION_LABELS[self.correct_index]
            selected_label = OPTION_LABELS[index]

            if index == self.correct_index:
                result_text = random.choice(CORRECT_RESPONSES)
                # Registrar los puntos en la base de datos
                new_points, new_wins, just_won = database.add_trivia_points(
                    interaction.user.id, interaction.user.name, 1
                )
                
                color = discord.Color.green()
                title = "✅ ¡Correcto!"
                
                if just_won:
                    result_text += f"\n\n🎉 **¡WOW! Llegaste a {new_points} puntos.** ¡Sumaste una VICTORIA OFICIAL en la tabla general! 🏆"
                else:
                    result_text += f"\n*Llevas {new_points} puntos en total.*"
            else:
                template = random.choice(WRONG_RESPONSES)
                result_text = template.format(correct=correct_label)
                color = discord.Color.red()
                title = "❌ ¡Incorrecto!"

            # Colorear botones para mostrar respuesta correcta
            for child in self.children:
                child.disabled = True  # type: ignore
                cid = child.custom_id  # type: ignore
                if cid == f"trivia_option_{self.correct_index}":
                    child.style = discord.ButtonStyle.success  # type: ignore
                elif cid == f"trivia_option_{index}" and index != self.correct_index:
                    child.style = discord.ButtonStyle.danger  # type: ignore
                else:
                    child.style = discord.ButtonStyle.secondary  # type: ignore

            embed = discord.Embed(title=title, color=color)
            embed.add_field(
                name="Pregunta",
                value=self.question_data["question"],
                inline=False,
            )
            embed.add_field(
                name="Tu respuesta",
                value=f"{selected_label}) {self.question_data['options'][index]}",
                inline=True,
            )
            embed.add_field(
                name="Respuesta correcta",
                value=f"{correct_label}) {self.question_data['options'][self.correct_index]}",
                inline=True,
            )
            embed.add_field(name="\u200b", value=result_text, inline=False)

            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()

        return callback

    async def on_timeout(self):
        if self.answered:
            return

        self.answered = True
        timeout_text = random.choice(TIMEOUT_RESPONSES)
        correct_label = OPTION_LABELS[self.correct_index]

        for child in self.children:
            child.disabled = True  # type: ignore
            cid = child.custom_id  # type: ignore
            if cid == f"trivia_option_{self.correct_index}":
                child.style = discord.ButtonStyle.success  # type: ignore
            else:
                child.style = discord.ButtonStyle.secondary  # type: ignore

        embed = discord.Embed(title="⏰ ¡Tiempo agotado!", color=discord.Color.dark_grey())
        embed.add_field(
            name="Pregunta",
            value=self.question_data["question"],
            inline=False,
        )
        embed.add_field(
            name="Respuesta correcta",
            value=f"{correct_label}) {self.question_data['options'][self.correct_index]}",
            inline=False,
        )
        embed.add_field(name="\u200b", value=timeout_text, inline=False)

        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


# ─────────────────────────────────────────────
# Funciones de apoyo para armar los juegos
# ─────────────────────────────────────────────

def get_rps_view() -> tuple[discord.Embed, RPSView]:
    """Devuelve un embed y view listos para jugar Piedra, Papel o Tijera."""
    embed = discord.Embed(
        title="🪨✂️📄 ¡Piedra, Papel o Tijera!",
        description=(
            "a ver si me ganas 😏\n"
            "elige tu jugada y ya veremos quién es la mejor~"
        ),
        color=discord.Color.purple(),
    )
    embed.set_footer(text="tienes 30 segundos ⏳")
    view = RPSView()
    return embed, view


_trivia_bank = None

def _load_trivia_bank():
    global _trivia_bank
    if _trivia_bank is not None:
        return _trivia_bank
    
    import os
    path = "trivia_bank.json"
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                _trivia_bank = json.load(f)
                return _trivia_bank
        except Exception as e:
            print(f"Error loading trivia_bank.json: {e}")
            
    # Fallback de emergencia
    _trivia_bank = [
        {
            "question": "¿En qué año se lanzó Discord? (Ups, no encontré mi archivo de preguntas 😅)",
            "options": ["2013", "2014", "2015", "2016"],
            "answer": 2
        }
    ]
    return _trivia_bank


async def get_trivia_question() -> tuple[discord.Embed, TriviaView]:
    """Genera un embed y view con una pregunta de trivia aleatoria desde el banco local."""
    bank = _load_trivia_bank()
    question_data = random.choice(bank)

    options_text = "\n".join(
        f"**{OPTION_LABELS[i]})** {opt}"
        for i, opt in enumerate(question_data["options"])
    )

    embed = discord.Embed(
        title="🧠 ¡Trivia Time!",
        description=(
            f"**{question_data['question']}**\n\n"
            f"{options_text}"
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="tienes 15 segundos para responder ⏳ apúrale!")

    view = TriviaView(question_data)
    return embed, view


# ─────────────────────────────────────────────
# Piedra, Papel o Tijera (Multijugador)
# ─────────────────────────────────────────────

class RPSMultiplayerView(View):
    def __init__(self, player1: discord.User | discord.Member, player2: discord.User | discord.Member, *, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.player1 = player1
        self.player2 = player2
        self.p1_choice: str | None = None
        self.p2_choice: str | None = None
        self.message: discord.Message | None = None

    async def _handle_choice(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id not in (self.player1.id, self.player2.id):
            await interaction.response.send_message("este juego no es tuyo metiche 😒", ephemeral=True)
            return

        if interaction.user.id == self.player1.id:
            if self.p1_choice:
                await interaction.response.send_message("ya elegiste! espera a que tire el otro", ephemeral=True)
                return
            self.p1_choice = choice
        else:
            if self.p2_choice:
                await interaction.response.send_message("ya elegiste! espera a que tire el otro", ephemeral=True)
                return
            self.p2_choice = choice

        # Si faltan por tirar, avisamos en secreto al que tiró
        if not self.p1_choice or not self.p2_choice:
            await interaction.response.send_message(f"Elegiste {RPS_CHOICES[choice]} shhh 🤫", ephemeral=True)
            return

        # Ambos tiraron, revelar
        await interaction.response.defer()
        
        outcome = RPS_OUTCOMES[self.p1_choice][self.p2_choice]
        
        if outcome == "win":
            title = f"🏆 ¡Ganó {self.player1.display_name}!"
            color = discord.Color.green()
            desc = f"**{self.player2.display_name}** fue aplastado."
            database.add_rps_win(self.player1.id, self.player1.name)
        elif outcome == "lose":
            title = f"🏆 ¡Ganó {self.player2.display_name}!"
            color = discord.Color.green()
            desc = f"**{self.player1.display_name}** fue aplastado."
            database.add_rps_win(self.player2.id, self.player2.name)
        else:
            title = "🤝 ¡Empate!"
            color = discord.Color.gold()
            desc = "Ambos pensaron igual."

        embed = discord.Embed(title=title, description=desc, color=color)
        embed.add_field(name=self.player1.display_name, value=f"{RPS_CHOICES[self.p1_choice]} {self.p1_choice.capitalize()}", inline=True)
        embed.add_field(name="VS", value="⚡", inline=True)
        embed.add_field(name=self.player2.display_name, value=f"{RPS_CHOICES[self.p2_choice]} {self.p2_choice.capitalize()}", inline=True)

        for child in self.children:
            child.disabled = True # type: ignore

        if self.message:
            await self.message.edit(embed=embed, view=self)
        self.stop()

    @discord.ui.button(label="Piedra", emoji="🪨", style=discord.ButtonStyle.secondary)
    async def piedra_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, "piedra")

    @discord.ui.button(label="Tijera", emoji="✂️", style=discord.ButtonStyle.secondary)
    async def tijera_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, "tijera")

    @discord.ui.button(label="Papel", emoji="📄", style=discord.ButtonStyle.secondary)
    async def papel_button(self, interaction: discord.Interaction, button: Button):
        await self._handle_choice(interaction, "papel")

    async def on_timeout(self):
        if self.p1_choice and self.p2_choice:
            return
        for child in self.children:
            child.disabled = True # type: ignore
        embed = discord.Embed(title="⏰ Tiempo agotado", description="Alguien tuvo miedo y huyó de la batalla...", color=discord.Color.red())
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


def get_rps_multiplayer_view(player1: discord.User | discord.Member, player2: discord.User | discord.Member) -> tuple[discord.Embed, RPSMultiplayerView]:
    embed = discord.Embed(
        title="⚔️ Duelo: Piedra, Papel o Tijera",
        description=f"{player1.mention} reta a {player2.mention}\n\nElijan su jugada abajo. ¡Es secreto hasta que ambos tiren!",
        color=discord.Color.purple(),
    )
    embed.set_footer(text="tienen 60 segundos ⏳")
    view = RPSMultiplayerView(player1, player2)
    return embed, view


# ─────────────────────────────────────────────
# Tic Tac Toe (Tres en Raya)
# ─────────────────────────────────────────────

class TicTacToeButton(Button):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        assert self.view is not None
        view: TicTacToeView = self.view # type: ignore

        if interaction.user.id not in (view.player_x.id, view.player_o.id):
            await interaction.response.send_message("tú no estás jugando, bájale 😒", ephemeral=True)
            return

        is_x_turn = (view.current_player == view.player_x)
        if interaction.user.id != view.current_player.id:
            await interaction.response.send_message("no es tu turno trampos@ 😤", ephemeral=True)
            return

        self.style = discord.ButtonStyle.primary if is_x_turn else discord.ButtonStyle.danger
        self.label = "X" if is_x_turn else "O"
        self.disabled = True
        view.board[self.y][self.x] = view.current_player.id

        winner = view.check_winner()
        if winner is not None:
            await view.finish_game(interaction, winner)
            return
            
        # Cambiar el turno al otro jugador
        view.current_player = view.player_o if is_x_turn else view.player_x
        
        # Si es el turno de Lulu, que haga su jugada solita antes de actualizar Discord
        if view.current_player.bot:
            bot_x, bot_y = view.calculate_bot_move()
            if bot_x is not None and bot_y is not None:
                view.board[bot_y][bot_x] = view.current_player.id
                
                # Encontrar el botón que Lulu "apretó" y actualizarlo
                for child in view.children:
                    b = child # type: ignore
                    if hasattr(b, 'x') and b.x == bot_x and b.y == bot_y:
                        b.style = discord.ButtonStyle.danger # Lulu siempre es la O en esta versión
                        b.label = "O"
                        b.disabled = True
                        break
                
                # Checar si Lulu acaba de ganar
                winner = view.check_winner()
                if winner is not None:
                    await view.finish_game(interaction, winner)
                    return
                    
                # Regresarle el turno al humano
                view.current_player = view.player_x

        # Actualizar el mensaje normal
        desc = f"Turno de {view.current_player.mention} ({'X' if view.current_player == view.player_x else 'O'})"
        embed = discord.Embed(title="❌⭕ Tic Tac Toe", description=desc, color=discord.Color.blue())
        await interaction.response.edit_message(embed=embed, view=view)


class TicTacToeView(View):
    def __init__(self, player1: discord.User | discord.Member, player2: discord.User | discord.Member):
        super().__init__(timeout=120.0)
        self.player_x = player1
        self.player_o = player2
        self.current_player = player1
        self.board = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        self.message: discord.Message | None = None

        for y in range(3):
            for x in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_winner(self) -> int | None:
        b = self.board
        # Filas y columnas
        for i in range(3):
            if b[i][0] == b[i][1] == b[i][2] and b[i][0] != 0:
                return b[i][0]
            if b[0][i] == b[1][i] == b[2][i] and b[0][i] != 0:
                return b[0][i]
        
        # Diagonales
        if b[0][0] == b[1][1] == b[2][2] and b[0][0] != 0:
            return b[0][0]
        if b[0][2] == b[1][1] == b[2][0] and b[0][2] != 0:
            return b[0][2]
        
        # Empate?
        if all(b[y][x] != 0 for y in range(3) for x in range(3)):
            return 0 # Empate
            
        return None

    async def finish_game(self, interaction: discord.Interaction, winner: int):
        for child in self.children:
            child.disabled = True # type: ignore
        
        if winner == self.player_x.id:
            desc = f"🏆 ¡**{self.player_x.display_name}** ganó con las X!"
            color = discord.Color.green()
            if not self.player_x.bot:
                database.add_tictactoe_win(self.player_x.id, self.player_x.name)
        elif winner == self.player_o.id:
            desc = f"🏆 ¡**{self.player_o.display_name}** ganó con las O!"
            color = discord.Color.green()
            if not self.player_o.bot:
                database.add_tictactoe_win(self.player_o.id, self.player_o.name)
        else:
            desc = "🤝 ¡Empate! Nadie gana."
            color = discord.Color.gold()
        
        embed = discord.Embed(title="❌⭕ Tic Tac Toe", description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    def calculate_bot_move(self) -> tuple[int | None, int | None]:
        b = self.board
        bot_id = self.player_o.id
        human_id = self.player_x.id
        
        # Función interna para checar si hay una línea a punto de completarse
        def find_winning_spot(target_id: int) -> tuple[int | None, int | None]:
            # Filas
            for y in range(3):
                row = [b[y][0], b[y][1], b[y][2]]
                if row.count(target_id) == 2 and row.count(0) == 1:
                    return (row.index(0), y)
            # Columnas
            for x in range(3):
                col = [b[0][x], b[1][x], b[2][x]]
                if col.count(target_id) == 2 and col.count(0) == 1:
                    return (x, col.index(0))
            # Diagonales
            d1 = [b[0][0], b[1][1], b[2][2]]
            if d1.count(target_id) == 2 and d1.count(0) == 1:
                idx = d1.index(0)
                return (idx, idx)
            d2 = [b[0][2], b[1][1], b[2][0]]
            if d2.count(target_id) == 2 and d2.count(0) == 1:
                idx = d2.index(0)
                return (2 - idx, idx)
            return None, None

        # 1. Intentar ganar el juego de una vez
        wx, wy = find_winning_spot(bot_id)
        if wx is not None and wy is not None:
            return wx, wy

        # 2. Intentar bloquear al humano para que no gane
        bx, by = find_winning_spot(human_id)
        if bx is not None and by is not None:
            return bx, by

        # 3. Tomar el centro si está libre (es la mejor estrategia)
        if b[1][1] == 0:
            return 1, 1

        # 4. Agarrar cualquier lugar al azar si ya no hay de otra
        empty = []
        for y in range(3):
            for x in range(3):
                if b[y][x] == 0:
                    empty.append((x, y))
        
        if empty:
            return random.choice(empty)
        return None, None

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True # type: ignore
        embed = discord.Embed(title="⏰ Tiempo agotado", description="El juego fue abandonado...", color=discord.Color.red())
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


def get_tictactoe_view(player1: discord.User | discord.Member, player2: discord.User | discord.Member) -> tuple[discord.Embed, TicTacToeView]:
    embed = discord.Embed(
        title="❌⭕ Tic Tac Toe",
        description=f"**X**: {player1.mention}\n**O**: {player2.mention}\n\nEmpieza tirando las X: {player1.mention}",
        color=discord.Color.blue(),
    )
    view = TicTacToeView(player1, player2)
    return embed, view
