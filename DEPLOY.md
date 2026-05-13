# Heartbeat Backend — Guía de Despliegue (Primera vez)

## Requisitos previos
- VPS con Ubuntu 22.04 (o similar)
- aaPanel instalado
- Acceso SSH como root

---

## 1. Conectarse al VPS por SSH

```bash
ssh root@<IP_DEL_VPS>
```

---

## 2. Instalar Docker y Docker Compose

```bash
# Instalar Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Verificar versión
docker --version

# Docker Compose (ya incluido en Docker Engine v2+)
docker compose version
```

Si `docker compose` no funciona, instalar el plugin:
```bash
apt-get install docker-compose-plugin -y
```

---

## 3. Clonar el repositorio

```bash
mkdir -p /www/wwwroot
cd /www/wwwroot
git clone https://github.com/TU_USUARIO/heartbeat-backend.git
cd heartbeat-backend
```

---

## 4. Crear el archivo `.env`

```bash
cp .env.example .env
nano .env
```

Rellenar todos los valores:

```env
DATABASE_URL=postgresql+asyncpg://heartbeat_user:TU_PASSWORD_SEGURO@db:5432/heartbeat
POSTGRES_DB=heartbeat
POSTGRES_USER=heartbeat_user
POSTGRES_PASSWORD=TU_PASSWORD_SEGURO
SECRET_KEY=genera-uno-con-openssl-rand-hex-32
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_DAYS=90
FIREBASE_CREDENTIALS_PATH=/app/firebase-credentials.json
```

Generar `SECRET_KEY`:
```bash
openssl rand -hex 32
```

---

## 5. Crear el archivo de credenciales de Firebase

Descarga el archivo JSON desde Firebase Console:
`Firebase Console → Project Settings → Service Accounts → Generate new private key`

```bash
nano /www/wwwroot/heartbeat-backend/firebase-credentials.json
# Pegar el contenido del JSON descargado
```

> **IMPORTANTE:** Este archivo nunca debe subirse al repositorio (ya está en `.gitignore`).

---

## 6. Levantar los contenedores

```bash
cd /www/wwwroot/heartbeat-backend
docker compose up -d --build
```

Verificar que están corriendo:
```bash
docker compose ps
```

Deberías ver `db` y `api` en estado `running`.

---

## 7. Ejecutar las migraciones de base de datos

```bash
docker compose exec api alembic upgrade head
```

---

## 8. Configurar Nginx en aaPanel

### 8.1 Crear el sitio web
1. Ir a aaPanel → **Websites** → **Add Site**
2. Dominio: `api.laaf.lat`
3. PHP: seleccionar "Pure Static" o "No PHP"

### 8.2 Activar SSL con Let's Encrypt
1. Entrar al sitio → **SSL**
2. Seleccionar **Let's Encrypt**
3. Click en **Apply**

### 8.3 Configurar Nginx como reverse proxy
Ir al sitio → **Config** (o editar el archivo de configuración manualmente).

Reemplazar el contenido dentro del bloque `server` con:

```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name api.laaf.lat;

    # SSL (aaPanel lo gestiona automáticamente con Let's Encrypt)
    ssl_certificate    /www/server/panel/vhost/cert/api.laaf.lat/fullchain.pem;
    ssl_certificate_key /www/server/panel/vhost/cert/api.laaf.lat/privkey.pem;

    # Redirect HTTP to HTTPS
    if ($scheme = http) {
        return 301 https://$host$request_uri;
    }

    # Proxy hacia FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Configuración especial para WebSockets
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

Después de guardar, recargar Nginx:
```bash
nginx -t && nginx -s reload
```

---

## 9. Verificar que todo funciona

```bash
# Estado de los contenedores
docker compose ps

# Logs de la API
docker compose logs api --tail=50

# Health check
curl https://api.laaf.lat/health
# Debe responder: {"status":"ok"}
```

---

## 10. Configurar GitHub Actions para deploys automáticos

En tu repositorio de GitHub, ir a **Settings → Secrets and variables → Actions** y agregar:

| Secret | Valor |
|--------|-------|
| `VPS_HOST` | IP o dominio del VPS (ej: `123.456.789.0`) |
| `VPS_USER` | Usuario SSH (normalmente `root`) |
| `VPS_SSH_KEY` | Contenido de tu llave privada SSH (`~/.ssh/id_rsa`) |

A partir de ahora, cada `git push` a `main` desplegará automáticamente.

---

## Comandos útiles post-despliegue

```bash
# Ver logs en tiempo real
docker compose logs -f api

# Reiniciar solo la API (sin reconstruir)
docker compose restart api

# Reconstruir y reiniciar todo
docker compose down && docker compose up -d --build

# Ejecutar migraciones
docker compose exec api alembic upgrade head

# Ver migraciones aplicadas
docker compose exec api alembic history
```
