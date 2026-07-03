import database

# Inicializa la base de datos (crea tablas)
database.init_db()

# Añade una memoria de imagen de prueba
user_id = 123456789
username = "tester"
summary = "Foto de un gato con gorro rojo y una taza de café."

database.add_image_memory(user_id, username, summary)

# Recupera y muestra las memorias para el usuario
mems = database.get_image_memories(user_id, limit=5)
print(mems)
