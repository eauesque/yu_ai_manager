# Руководство по установке FFmpeg

Tag Database использует ffmpeg для генерации миниатюр видеофайлов (WebM, MP4 и т.д.).

## Windows

### Вариант 1: Scoop (рекомендуется)
```powershell
# Установить Scoop (если не установлен)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Установить ffmpeg
scoop install ffmpeg
```

### Вариант 2: Chocolatey
```powershell
choco install ffmpeg
```

### Вариант 3: Ручная загрузка
1. Скачать с: https://www.gyan.dev/ffmpeg/builds/
2. Распаковать в `C:\ffmpeg`
3. Добавить `C:\ffmpeg\bin` в PATH через «Переменные среды»
4. Перезапустить терминал

---

## macOS

### Homebrew (рекомендуется)
```bash
brew install ffmpeg
```

---

## Linux

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install ffmpeg
```

### Fedora
```bash
sudo dnf install ffmpeg
```

### Arch
```bash
sudo pacman -S ffmpeg
```

---

## Проверка установки

```bash
ffmpeg -version
```

---

## Устранение неполадок

### Ошибка «ffmpeg not installed»

1. Проверить установку: `ffmpeg -version`
2. Перезапустить терминал / PowerShell
3. Перезапустить WebUI
4. Проверить настройки PATH

### Миниатюры не генерируются

**Возможные причины**:
- Повреждённый видеофайл
- Неподдерживаемый кодек
- Таймаут ffmpeg (более 10 секунд)

**Отладка**:
```bash
# Тест вручную
ffmpeg -i your_video.webm -ss 00:00:01 -vframes 1 test_thumb.jpg
```

---

## Заметки о производительности

- Первичная генерация миниатюр: ~1–3 сек
- Кэшированные миниатюры: < 100 мс
- Таймаут: 10 сек на видео
