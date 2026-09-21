import json
import re
from urllib.parse import quote_plus

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


# ------------------------------------------------------------
# YouTube links
# ------------------------------------------------------------

def _youtube_search_link(query):
    return "https://www.youtube.com/results?search_query=" + quote_plus(query)


# YouTube link for an exercise in the dropdown.
# To use a specific video, add  "youtube": "https://youtu.be/..."
# to that exercise in mindfulness.json and it will be used instead.
def get_youtube_link(title):
    exercise = get_exercise(title)

    if exercise and exercise.get("youtube"):
        return exercise["youtube"]

    # remove the "(10:45)" / "(5 min)" part from the title
    name = re.sub(r"\s*\(.*?\)", "", title).strip()
    return _youtube_search_link(name + " mindfulness exercise")


# ------------------------------------------------------------
# Video suggestion for normal chat messages
# (keywords the user types  ->  video to suggest)
# ------------------------------------------------------------

VIDEO_TOPICS = [
    (["panic", "grounding"],
     "5-4-3-2-1 grounding exercise",
     "5 4 3 2 1 grounding exercise for panic"),

    (["breath", "anxiety", "anxious"],
     "Guided breathing exercise",
     "guided breathing exercise for anxiety"),

    (["sleep", "insomnia"],
     "Guided meditation for sleep",
     "guided meditation for sleep"),

    (["relax", "tense", "tension", "muscle"],
     "Progressive muscle relaxation",
     "progressive muscle relaxation guided"),

    (["stress", "overwhelm", "calm"],
     "Guided meditation for stress relief",
     "guided meditation for stress relief"),

    (["meditat", "mindful"],
     "Beginner mindfulness meditation",
     "beginner mindfulness meditation guided"),

    (["depress", "sad", "hopeless", "low mood", "empty", "lonely"],
     "Coping with low mood and depression",
     "coping with depression tips and guided meditation"),

    (["exercise", "workout", "yoga", "self-care", "self care"],
     "Gentle yoga and self-care",
     "gentle yoga for mental health beginners"),

    (["stigma", "mental health awareness"],
     "Understanding mental health",
     "understanding mental health stigma explained"),
]


def _match_video(text):
    text = text.lower()

    for keywords, label, query in VIDEO_TOPICS:
        if any(k in text for k in keywords):
            return f"🎥 Try this: [{label} on YouTube]({_youtube_search_link(query)})"

    return None


def get_video_suggestion(message, response=""):
    """
    Always returns a YouTube link for a real chat message.
    1) keywords in the user's message
    2) keywords in the bot's answer
    3) a general wellbeing video (if none of the above matched)
    Only very short messages like "hi" / "thanks" get no link.
    """

    video = _match_video(message)

    if not video:
        video = _match_video(response)

    if not video:
        if len(message.split()) < 3:
            return None

        video = (
            "🎥 Try this: [Guided relaxation for mental wellbeing on YouTube]"
            f"({_youtube_search_link('guided relaxation for mental wellbeing')})"
        )

    return video


# ------------------------------------------------------------
# Video for each TOPIC in the Topics dropdown
# (title must match the title in topics.json)
# ------------------------------------------------------------

TOPIC_VIDEOS = {
    "Understanding Mental Health: Importance and Stigma":
        ("Why mental health matters", "importance of mental health and stigma explained"),
    "Understanding Mental Health: Causes and Effects":
        ("Causes and effects of mental health problems", "causes and effects of mental health disorders explained"),
    "Understanding Mental Health: Promotion and Prevention":
        ("Looking after your mental health", "how to promote and protect your mental health"),
    "Mental Health: Self-care and Exercise":
        ("Self-care and exercise for mental health", "self care and exercise for mental health"),
    "Understanding and Coping with Anxiety":
        ("Coping with anxiety", "how to cope with anxiety tips"),
    "Understanding and Coping with Depression":
        ("Coping with depression", "understanding and coping with depression"),
    "Understanding and Managing Stress":
        ("Managing stress", "how to manage stress techniques"),
}


def get_topic_video(title):
    """YouTube link text for a topic, or None if the topic is not in the list."""

    if title not in TOPIC_VIDEOS:
        return None

    label, query = TOPIC_VIDEOS[title]
    return f"🎥 Learn more: [{label} on YouTube]({_youtube_search_link(query)})"


# ------------------------------------------------------------
# Video shown with the TEST result
# ------------------------------------------------------------

TEST_VIDEOS = {
    "depression test":
        ("Coping with depression", "coping with depression tips"),
    "anxiety test":
        ("Calming anxiety", "guided breathing exercise for anxiety"),
}


def get_test_video(title):
    """YouTube link text for a test result, or None."""

    key = title.lower()

    if key not in TEST_VIDEOS:
        return None

    label, query = TEST_VIDEOS[key]
    return f"🎥 This may help: [{label} on YouTube]({_youtube_search_link(query)})"
