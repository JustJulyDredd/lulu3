#!/bin/bash
# setup_oci.sh – Script de automatización de despliegue en OCI
set -e

echo "=== Configurando el entorno en Oracle Cloud ==="

# 1. Actualizar el sistema
echo "[1/6] Actualizando el sistema..."
sudo apt update && sudo apt upgrade -y

# 2. Instalar dependencias esenciales
echo "[2/6] Instalando dependencias (Java 21, Python, venv, screen, git)..."
sudo apt install -y openjdk-21-jre-headless python3-pip python3-venv git screen iptables-persistent

# 3. Configurar Lulu Bot
echo "[3/4] Configurando entorno virtual para Lulu Bot..."
cd ~/lulu2
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 5. Configurar Lulu Bot
echo "[5/6] Configurando entorno virtual para Lulu Bot..."
cd ~/lulu2
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

if [ ! -f variables.env ]; then
  cp variables.env.example variables.env
  echo "=> Creado variables.env. Recuerda configurarlo antes de iniciar."
fi

# 4. Crear el servicio de systemd para Lulu Bot
echo "[4/4] Creando servicio systemd para Lulu Bot..."
sudo tee /etc/systemd/system/lulu.service > /dev/null <<EOF
[Unit]
Description=Lulu Discord Bot Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/lulu2
ExecStart=/home/ubuntu/lulu2/venv/bin/python /home/ubuntu/lulu2/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable lulu.service

echo "================================================"
echo "=== Configuración Completada con éxito ==="
echo "================================================"
echo "Instrucciones de uso:"
echo ""
echo "1. Para configurar y arrancar el bot:"
echo "   Edita el archivo: ~/lulu2/variables.env"
echo "   Y arranca el servicio con: sudo systemctl start lulu"
echo "================================================"
