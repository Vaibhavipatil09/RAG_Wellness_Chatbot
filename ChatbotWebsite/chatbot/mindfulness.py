import json

# load mindfulness exercises from json file
with open("ChatbotWebsite/static/mindfulness/mindfulness.json") as file:
    mindfulness_exercises = json.load(file)


# get the full exercise object by title - works for both "audio" and
# "activity" type exercises, since callers can check exercise["type"]
def get_exercise(title):
    for exercise in mindfulness_exercises["mindfulness_exercises"]:
        if exercise["title"] == title:
            return exercise
    return None
