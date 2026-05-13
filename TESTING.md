# Heartbeat Backend — Guía de Pruebas

Base URL: `https://api.laaf.lat` (o `http://localhost:8000` en local)

---

## Health Check

```bash
curl https://api.laaf.lat/health
# Respuesta esperada: {"status":"ok"}
```

---

## Flujo completo con REST (Postman / Insomnia / curl)

### Paso 1: Crear Usuario A

```bash
curl -X POST https://api.laaf.lat/api/v1/auth/create-user \
  -H "Content-Type: application/json" \
  -d '{"name": "Ana"}'
```

Respuesta esperada:
```json
{
  "user_id": "uuid-de-ana",
  "auth_token": "eyJ...",
  "pairing_code": "LUNA42",
  "name": "Ana"
}
```

**Guarda:** `TOKEN_A = auth_token`, `PAIRING_CODE = pairing_code`

---

### Paso 2: Crear Usuario B (unirse con el código)

```bash
curl -X POST https://api.laaf.lat/api/v1/auth/join-couple \
  -H "Content-Type: application/json" \
  -d '{"name": "Luis", "pairing_code": "LUNA42"}'
```

Respuesta esperada:
```json
{
  "user_id": "uuid-de-luis",
  "auth_token": "eyJ...",
  "couple_id": "uuid-de-la-pareja",
  "name": "Luis"
}
```

**Guarda:** `TOKEN_B = auth_token`

---

### Paso 3: Verificar /me de Usuario A

```bash
curl https://api.laaf.lat/api/v1/auth/me \
  -H "Authorization: Bearer TOKEN_A"
```

Respuesta esperada:
```json
{
  "user_id": "uuid-de-ana",
  "name": "Ana",
  "couple_id": "uuid-de-la-pareja",
  "partner_name": "Luis",
  "is_paired": true
}
```

---

### Paso 4: Registrar FCM token (simular que la app envió su token)

```bash
curl -X POST https://api.laaf.lat/api/v1/auth/refresh-fcm \
  -H "Authorization: Bearer TOKEN_B" \
  -H "Content-Type: application/json" \
  -d '{"fcm_token": "token-de-prueba-fcm"}'
```

Respuesta: `{"ok": true}`

---

### Paso 5: Enviar señal (trigger) desde A hacia B

```bash
curl -X POST https://api.laaf.lat/api/v1/trigger/send \
  -H "Authorization: Bearer TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Respuesta esperada (si B tiene WebSocket activo):
```json
{"delivered": true, "method": "websocket"}
```

Respuesta esperada (si B no tiene WebSocket pero sí FCM token):
```json
{"delivered": true, "method": "fcm"}
```

Respuesta esperada (si B está offline):
```json
{"delivered": false, "method": "offline"}
```

---

### Paso 6: Gestión de botones

**Crear botón:**
```bash
curl -X POST https://api.laaf.lat/api/v1/button/create \
  -H "Authorization: Bearer TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"label": "Abrazar a mi gruñona"}'
```

**Listar botones:**
```bash
curl https://api.laaf.lat/api/v1/button/list \
  -H "Authorization: Bearer TOKEN_A"
```

---

## Probar WebSocket en tiempo real

### Herramientas recomendadas:
- [Hoppscotch](https://hoppscotch.io) (web, gratis)
- [Simple WebSocket Client](https://chrome.google.com/webstore/detail/simple-websocket-client/) (extensión Chrome)
- [Postman](https://www.postman.com) (soporta WebSockets desde v9)

### Pasos:

1. **Abrir conexión como Usuario B:**
   ```
   URL: wss://api.laaf.lat/ws/UUID_DE_LUIS?token=TOKEN_B
   ```

2. **Abrir conexión como Usuario A (opcional, para ver confirmación):**
   ```
   URL: wss://api.laaf.lat/ws/UUID_DE_ANA?token=TOKEN_A
   ```

3. **Enviar ping desde cualquier conexión:**
   ```json
   {"type": "ping"}
   ```
   Respuesta esperada: `{"type": "pong"}`

4. **Desde Postman/curl, enviar trigger como A:**
   ```bash
   curl -X POST https://api.laaf.lat/api/v1/trigger/send \
     -H "Authorization: Bearer TOKEN_A" \
     -d '{}'
   ```

5. **Verificar que B recibe en el WebSocket:**
   ```json
   {
     "type": "incoming_trigger",
     "from_name": "Ana",
     "message": "Tu pareja te envió una señal ❤️",
     "timestamp": "2024-01-01T12:00:00Z"
   }
   ```

---

## Probar FCM

1. **Desconectar el WebSocket de B** (cerrar la pestaña o conexión)
2. **Enviar trigger desde A:**
   ```bash
   curl -X POST https://api.laaf.lat/api/v1/trigger/send \
     -H "Authorization: Bearer TOKEN_A" \
     -d '{}'
   ```
3. **Verificar en los logs del servidor:**
   ```bash
   docker compose logs api --tail=20
   ```
   Deberías ver algo como: `fcm_sent message_id=...`

> La notificación real en el celular se verifica cuando esté integrada la app Kotlin con Firebase.

---

## Probar rate limiting

Intentar crear más de 3 usuarios en un minuto:

```bash
for i in 1 2 3 4; do
  curl -X POST https://api.laaf.lat/api/v1/auth/create-user \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"Test$i\"}"
  echo ""
done
```

El 4to intento debe devolver HTTP 429.

---

## Documentación interactiva

Una vez desplegado, la documentación Swagger está disponible en:

```
https://api.laaf.lat/api/docs
```

Y ReDoc en:

```
https://api.laaf.lat/api/redoc
```

---

## Errores comunes y soluciones

| Error | Causa | Solución |
|-------|-------|----------|
| `401 INVALID_TOKEN` | JWT expirado o incorrecto | Hacer login de nuevo con `create-user` |
| `400 INVALID_PAIRING_CODE` | Código ya usado o inexistente | Verificar el código o crear nuevo usuario |
| `400 NOT_IN_COUPLE` | Usuario sin pareja asignada | Completar el emparejamiento primero |
| `429 RATE_LIMIT_EXCEEDED` | Demasiadas peticiones | Esperar 1 minuto |
| WebSocket cierra con `4001` | Token inválido o user_id no coincide | Verificar que el token y user_id sean del mismo usuario |
