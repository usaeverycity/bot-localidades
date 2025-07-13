from datetime import datetime

with open("log.txt", "a") as f:
    f.write(f"Me ejecuté a las {datetime.now()}\n")

print("Bot corriendo ok.")
