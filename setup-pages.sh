#!/bin/bash
# setup-pages.sh — Подготовка GitHub репозитория для Pages
# Запусти один раз после создания репозитория

set -e

REPO_NAME="$1"

if [ -z "$REPO_NAME" ]; then
    echo "Использование: ./setup-pages.sh username/repo-name"
    exit 1
fi

echo "📁 Создаю локальный репозиторий..."
mkdir -p pages-repo
cd pages-repo
git init
git checkout -b main

# Создаём базовый index.html
cat > index.html << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Design Bot — Gallery</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { 
    font-family: 'Georgia', serif;
    background: #0a0a0a; 
    color: #f5f5f5;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }
  h1 { font-size: 3rem; letter-spacing: -0.05em; margin-bottom: 0.5rem; }
  p { color: #888; font-size: 1.1rem; }
  a { color: #ff6b6b; text-decoration: none; }
</style>
</head>
<body>
  <h1>Design Bot</h1>
  <p>Generated designs appear in <code>/designs/</code></p>
</body>
</html>
EOF

mkdir -p designs
echo "/* placeholder */" > designs/.gitkeep

git add .
git commit -m "Initial setup for GitHub Pages"

echo "🔗 Добавляю remote..."
git remote add origin "https://github.com/${REPO_NAME}.git"

echo ""
echo "✅ Репозиторий готов!"
echo "Теперь выполни:"
echo "  git push -u origin main"
echo ""
echo "Затем в GitHub: Settings → Pages → Source → Deploy from branch → main"
