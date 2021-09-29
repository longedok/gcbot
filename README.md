Telegram bot for automatically deleting messages in group chats.

### Development

See `Makefile` for common operations during development, such as running docker compose 
or rebuilding and running bot image after changes.

Creating alembic migrations:

`alembic revision --autogenerate -m "revision name"`

Applying alembic migrations:

`alembic upgrade head`

