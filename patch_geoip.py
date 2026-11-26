import glob, re

for f in glob.glob("*.py"):
    src = open(f, encoding="utf-8").read()
    if "geoip=False" in src:
        open(f, "w", encoding="utf-8").write(src.replace("geoip=False", "geoip=False"))
        print("патчу:", f)

print("готово")
