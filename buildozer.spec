[app]
title = Capillimetry
package.name = capillimetry
package.domain = org.capillimetry
source.dir = .
source.include_exts = py,kv,png,jpg,txt,csv
version = 0.1
requirements = python3,kivy
orientation = landscape
fullscreen = 0
android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 23
android.ndk = 25b
android.archs = arm64-v8a
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1

android.ndk_api = 23
p4a.bootstrap = sdl2




