# Design Bot 🎨

Telegram бот-дейнер: описываешь дизайн → получаешь HTML на GitHub Pages.

## Установка

```bash
cd design-bot
pip install -r requirements.txt
cp .env.example .env
# Заполни .env своими ключами
python bot.py
```

## Настройка .env

| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен от @BotFather |
| `OPENROUTER_API_KEY` | Ключ от openrouter.ai |
| `OPENROUTER_MODEL` | Модель (по умолчанию `anthropic/claude-sonnet-4`) |
| `GITHUB_TOKEN` | GitHub Personal Access Token |
| `GITHUB_REPO` | Репозиторий (`username/repo`) |
| `GITHUB_BRANCH` | Ветка (по умолчанию `main`) |

## GitHub Pages setup

1. Создай репозиторий на GitHub (например `design-pages`)
2. Запуши базовый `index.html` (см. `setup-pages.sh`)
3. В GitHub: **Settings → Pages → Source → Deploy from branch → main**
4. Pages URL будет: `https://username.github.io/design-pages/`

## Использование

В боте просто пишешь текст:
- "Лендинг для пиццерии, неоновый стиль, 80-е"
- "Портфолио UI дизайнера, минимализм, чёрно-белый"
- "Карточка SaaS продукта для AI-стартапа"

Бот сгенерирует HTML и пришлёт ссылку.
