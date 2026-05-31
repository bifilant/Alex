# Capillimetry Android APK

Это Android/Kivy версия вашего Python/Tkinter приложения «Капилляриметрия».

## Что сделано

- Убраны Tkinter и Matplotlib/TkAgg — они плохо подходят для Android.
- Расчётная логика вынесена в `calculations.py`.
- Интерфейс сделан на Kivy.
- Графики сделаны через Kivy Canvas, без Matplotlib — это менее глючный вариант для APK.
- Есть ввод исходных данных, таблица ступеней, расчёт, drag точек на графиках, экспорт CSV.
- Excel export заменён на CSV, потому что openpyxl в Android APK тяжелее и чаще ломает сборку.

## Сборка APK на Linux / WSL2 / Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-pip git zip unzip openjdk-17-jdk autoconf automake libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev
python3 -m pip install --user buildozer cython
cd CapillAPK
buildozer android debug
```

Готовый APK появится в:

```text
bin/capillimetry-0.1-arm64-v8a_armeabi-v7a-debug.apk
```

## Сборка через GitHub Actions

1. Создайте новый репозиторий на GitHub.
2. Загрузите туда содержимое папки `CapillAPK`.
3. Откройте вкладку **Actions**.
4. Запустите workflow **Build Android APK**.
5. Скачайте artifact `capillimetry-apk`.

## Установка на Android

Перед установкой включите разрешение установки APK из неизвестных источников.

```bash
adb install bin/*.apk
```

Или просто перекиньте APK на телефон и откройте файл.

## Важное отличие от Windows версии

Это не 1:1 перенос пиксель-в-пиксель. Tkinter-код переписан под Android. Расчёты сохранены по смыслу, но интерфейс сделан проще и стабильнее для телефона/планшета.
