import pyttsx3

def speak(text, filename="audio.mp3"):
    engine = pyttsx3.init()
    engine.setProperty("rate", 150)

    engine.save_to_file(text, filename)
    engine.runAndWait()

    return filename
