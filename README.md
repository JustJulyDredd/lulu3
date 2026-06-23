# 🛸 Lulu 3 - Discord Bot

Lulu 3 es un bot de Discord interactivo con **personalidad adaptativa** y **memoria a largo plazo**. Diseñado para integrarse en servidores de comunidad, Lulu actúa como un miembro más del servidor, adaptando su tono y actitud basándose en el historial de conversaciones y en cómo la trata cada usuario.

---

## 💫 Historia y Personalidad (Lore)

Lulu es una morra de 16 años, originaria del planeta **Nebulon-9**, que pasa su tiempo en Discord como cualquier adolescente normal. 

* **Estilo de habla**: Informal, relajada y muy natural. Utiliza jerga común de internet y Discord (`jaja`, `xd`, `ntp`, `nel`, `sip`, etc.). No habla como un asistente de IA formal ni estructurado.
* **Intereses**: Le encantan los doritos, el chocolate, los videojuegos, la música de sintetizadores y ver series.
* **Actitud Dinámica**: Su comportamiento cambia según el usuario:
  * **Amigos/Gente amable**: Cariñosa, divertida, bromista.
  * **Usuarios nuevos**: Curiosa y abierta.
  * **Gente grosera o tóxica**: Sarcástica, cortante, directa. Se defiende y no se queda callada.

---

## 🚀 Características Principales

### 1. Memoria a Largo Plazo Adaptativa 🧠
A diferencia de otros bots, Lulu tiene memoria persistente integrada con una base de datos SQLite. Periódicamente consolida los recuerdos de las conversaciones con cada usuario para actualizar su perfil:
* Gustos y pasatiempos compartidos.
* Actitud del usuario hacia ella (amigable, tóxica, grosera).
* Tono sugerido de respuesta y nivel de confianza (nula, baja, media, alta, muchísima).

### 2. Comandos de Barra (Slash Commands) 🎮
Lulu incluye un repertorio de comandos interactivos y minijuegos:
* `/remember`: Consulta qué recuerdos y nivel de confianza tiene Lulu sobre ti.
* `/cumple`: Registra tu cumpleaños para que Lulu te felicite cuando llegue el día.
* `/gato`: Juega al Tres en Raya (Tic Tac Toe) contra Lulu o contra un amigo en el chat.
* `/rps`: Juega a Piedra, Papel o Tijera contra la IA o contra otro usuario.
* `/trivia`: Lulu te hará una pregunta de cultura general para ponerte a prueba.
* `/ranking_juegos`: Muestra la tabla de clasificación de los mejores jugadores de minijuegos.
* `/status`: Consulta cuánto tiempo falta para poder volver a usar el comando de bump de Disboard.
* `/ranking`: Muestra el ranking de miembros del servidor según su cantidad de bumps realizados.

### 3. Recordatorio de Bumps (Disboard) ⏰
Monitorea los comandos de bump del servidor y notifica en el canal configurado cuando el servidor esté listo para ser "empujado" nuevamente.

### 4. Modo Lurker (Lurking) 👾
Lulu puede "espiar" canales específicos y responder de forma espontánea para sumarse a la conversación de manera casual y natural.

---

## 🛠️ Configuración e Instalación

### Requisitos previos
* Python 3.8 o superior.
* Una cuenta de Discord Developer con un Bot Token.

### Configuración de variables de entorno
Crea un archivo llamado `variables.env` en la raíz del proyecto basándote en [variables.env.example](variables.env.example):

```env
# Discord Token
DISCORD_TOKEN=tu_token_de_discord_aqui

# Proveedor de LLM (google | openrouter | huggingface | ollama)
LLM_PROVIDER=google

# API Keys según el proveedor elegido
GEMINI_API_KEY=tu_gemini_api_key
OPENROUTER_API_KEY=
HUGGINGFACE_API_TOKEN=
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b

# Configuración de canales de Discord
BUMP_INTERVAL_MINUTES=120
BUMP_CHANNEL_ID=id_del_canal_de_bumps
ALLOWED_CHANNEL_IDS=ids_de_canales_permitidos_separados_por_coma
WELCOME_CHANNEL_ID=id_del_canal_de_bienvenida
LURK_CHANNEL_IDS=ids_de_canales_de_lurk_separados_por_coma
DATABASE_PATH=lulu_bot.db
```

### Instalación

1. Clona el repositorio:
   ```bash
   git clone https://github.com/JustJulyDredd/lulu3.git
   cd lulu3
   ```
2. Crea un entorno virtual e instala las dependencias:
   ```bash
   python -m venv venv
   source venv/bin/activate  # En Linux/macOS
   # venv\Scripts\activate  # En Windows
   pip install -r requirements.txt
   ```
3. Ejecuta el bot:
   ```bash
   python bot.py
   ```
