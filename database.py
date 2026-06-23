import sqlite3
import time
from typing import Dict, List, Optional
from config import DATABASE_PATH


def get_db_connection() -> sqlite3.Connection:
    """Conecta a la base de datos y activa WAL para accesos concurrentes."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    """Crea las tablas necesarias si aún no existen."""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bump_status (
                channel_id INTEGER PRIMARY KEY,
                next_bump_time REAL NOT NULL,
                reminder_sent INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                personality_summary TEXT DEFAULT 'Un nuevo conocido. Aún no se han tenido conversaciones profundas con él.',
                interaction_count INTEGER DEFAULT 0,
                last_seen REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                message_content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                is_bot INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS birthdays (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                month INTEGER NOT NULL,
                day INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bump_stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                bump_count INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trivia_stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                points INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rps_stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                wins INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tictactoe_stats (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                wins INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS image_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                summary TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
            """
        )
        conn.commit()


# --- BUMP ---

def set_bump_time(channel_id: int, next_bump_time: float) -> None:
    """Guarda cuándo toca el próximo bump para un canal."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO bump_status (channel_id, next_bump_time, reminder_sent)
            VALUES (?, ?, 0)
            ON CONFLICT(channel_id) DO UPDATE SET
                next_bump_time = excluded.next_bump_time,
                reminder_sent = 0
            """,
            (channel_id, next_bump_time),
        )
        conn.commit()


def get_pending_reminders(current_time: float) -> List[Dict]:
    """Devuelve los canales cuyo bump ya venció y aún no recibieron recordatorio."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT channel_id, next_bump_time FROM bump_status
            WHERE next_bump_time <= ? AND reminder_sent = 0
            """,
            (current_time,),
        )
        return [dict(row) for row in cursor.fetchall()]


def mark_reminder_sent(channel_id: int) -> None:
    """Marca que ya se envió el recordatorio de bump."""
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE bump_status SET reminder_sent = 1
            WHERE channel_id = ?
            """,
            (channel_id,),
        )
        conn.commit()


def get_last_bump_info(channel_id: int) -> Optional[Dict]:
    """Devuelve la información del último bump de un canal."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT next_bump_time, reminder_sent FROM bump_status WHERE channel_id = ?",
            (channel_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# --- PERFIL DE USUARIO ---

def get_user_profile(user_id: int, username: str) -> Dict:
    """Devuelve el perfil del usuario o crea uno nuevo si aún no existe."""
    now = time.time()
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()

        if row:
            if row["username"] != username:
                conn.execute(
                    "UPDATE user_profiles SET username = ? WHERE user_id = ?",
                    (username, user_id),
                )
                conn.commit()
            return dict(row)

        default_summary = (
            f"Un nuevo conocido llamado {username}. Aún no se han tenido conversaciones profundas con él, "
            "pero te gustaría conocerlo."
        )
        conn.execute(
            """
            INSERT INTO user_profiles (user_id, username, personality_summary, interaction_count, last_seen)
            VALUES (?, ?, ?, 0, ?)
            """,
            (user_id, username, default_summary, now),
        )
        conn.commit()

        return {
            "user_id": user_id,
            "username": username,
            "personality_summary": default_summary,
            "interaction_count": 0,
            "last_seen": now,
        }


def update_user_profile_summary(user_id: int, summary: str) -> None:
    """Actualiza la descripción que Lulu tiene del usuario."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE user_profiles SET personality_summary = ? WHERE user_id = ?",
            (summary, user_id),
        )
        conn.commit()


def increment_user_interactions(user_id: int) -> None:
    """Incrementa el contador de interacciones del usuario."""
    now = time.time()
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE user_profiles SET
                interaction_count = interaction_count + 1,
                last_seen = ?
            WHERE user_id = ?
            """,
            (now, user_id),
        )
        conn.commit()


# --- HISTORIAL DE CHAT ---

def add_chat_message(
    channel_id: int,
    user_id: int,
    username: str,
    content: str,
    is_bot: bool,
    max_history: int = 50,
) -> None:
    """Guarda un mensaje y limpia los mensajes más antiguos del canal."""
    timestamp = time.time()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversation_history (channel_id, user_id, username, message_content, timestamp, is_bot)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (channel_id, user_id, username, content, timestamp, 1 if is_bot else 0),
        )
        conn.execute(
            """
            DELETE FROM conversation_history WHERE id IN (
                SELECT id FROM conversation_history
                WHERE channel_id = ?
                ORDER BY timestamp DESC
                LIMIT -1 OFFSET ?
            )
            """,
            (channel_id, max_history),
        )
        conn.commit()


def get_chat_history(channel_id: int, limit: int = 15) -> List[Dict]:
    """Trae los últimos mensajes de un canal, ordenados de lo más antiguo a lo más nuevo."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT user_id, username, message_content, timestamp, is_bot
            FROM conversation_history
            WHERE channel_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (channel_id, limit),
        )
        rows = cursor.fetchall()
        history = [dict(row) for row in rows]
        history.reverse()
        return history


def clear_history_for_channel(channel_id: int) -> None:
    """Limpia todo el historial de chat de un canal."""
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM conversation_history WHERE channel_id = ?",
            (channel_id,),
        )
        conn.commit()


# --- CUMPLEAÑOS ---

def set_birthday(user_id: int, username: str, month: int, day: int) -> None:
    """Registra o actualiza el cumpleaños de un usuario."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO birthdays (user_id, username, month, day)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                month = excluded.month,
                day = excluded.day
            """,
            (user_id, username, month, day),
        )
        conn.commit()


def get_birthday(user_id: int) -> Optional[Dict]:
    """Obtiene el cumpleaños guardado de un usuario."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM birthdays WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_todays_birthdays(month: int, day: int) -> List[Dict]:
    """Devuelve los cumpleaños que caen hoy."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM birthdays WHERE month = ? AND day = ?",
            (month, day),
        )
        return [dict(row) for row in cursor.fetchall()]


# --- STATS DE BUMP ---

def record_bump(user_id: int, username: str) -> None:
    """Suma un bump al contador del usuario."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO bump_stats (user_id, username, bump_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                bump_count = bump_count + 1
            """,
            (user_id, username),
        )
        conn.commit()


def get_bump_leaderboard(limit: int = 10) -> List[Dict]:
    """Obtiene la tabla de líderes de bumps."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT user_id, username, bump_count
            FROM bump_stats
            ORDER BY bump_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


# --- STATS DE TRIVIA ---

def add_trivia_points(user_id: int, username: str, points: int = 1) -> tuple[int, int, bool]:
    """Suma puntos de trivia y detecta si ganó una nueva victoria."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT points, wins FROM trivia_stats WHERE user_id = ?",
            (user_id,),
        )
        row = cursor.fetchone()

        current_points = row["points"] if row else 0
        current_wins = row["wins"] if row else 0

        new_points = current_points + points
        new_wins = current_wins
        just_won = False

        if new_points // 10 > current_wins:
            new_wins = new_points // 10
            just_won = True

        conn.execute(
            """
            INSERT INTO trivia_stats (user_id, username, points, wins)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                points = excluded.points,
                wins = excluded.wins
            """,
            (user_id, username, new_points, new_wins),
        )
        conn.commit()
        return new_points, new_wins, just_won


def get_trivia_leaderboard(limit: int = 10) -> List[Dict]:
    """Devuelve los líderes de trivia ordenados por victorias y puntos."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT user_id, username, points, wins
            FROM trivia_stats
            ORDER BY wins DESC, points DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


# --- MEMORIAS DE IMAGENES ---
def add_image_memory(user_id: int, username: str, summary: str) -> None:
    """Guarda un breve resumen/contexto de una imagen compartida por un usuario.

    Esto permite que Lulu recuerde qué mostró el usuario sin almacenar la imagen en sí.
    """
    timestamp = time.time()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO image_memories (user_id, username, summary, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, username, summary, timestamp),
        )
        conn.commit()


def get_image_memories(user_id: int, limit: int = 10) -> List[Dict]:
    """Devuelve los últimos resúmenes de imágenes compartidas por un usuario."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, user_id, username, summary, timestamp
            FROM image_memories
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# --- STATS DE PIEDRA PAPEL TIJERA ---

def add_rps_win(user_id: int, username: str) -> None:
    """Suma una victoria en Piedra Papel o Tijera."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO rps_stats (user_id, username, wins)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                wins = wins + 1
            """,
            (user_id, username),
        )
        conn.commit()


def get_rps_leaderboard(limit: int = 10) -> List[Dict]:
    """Devuelve los líderes de Piedra Papel o Tijera."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT user_id, username, wins
            FROM rps_stats
            ORDER BY wins DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


# --- STATS DE TRES EN RAYA ---

def add_tictactoe_win(user_id: int, username: str) -> None:
    """Registra una victoria en Tres en Raya."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO tictactoe_stats (user_id, username, wins)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                wins = wins + 1
            """,
            (user_id, username),
        )
        conn.commit()


def get_tictactoe_leaderboard(limit: int = 10) -> List[Dict]:
    """Devuelve los líderes del Gato ordenados por victorias."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT user_id, username, wins
            FROM tictactoe_stats
            ORDER BY wins DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
