from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import nltk
from nltk.tokenize import word_tokenize
from nltk.tokenize.treebank import TreebankWordDetokenizer
import logging
import spacy
import re
import os
import cv2
import time
import threading
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

logging.getLogger("pymongo").setLevel(logging.WARNING)


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MONGO_URI = os.getenv("MONGO_URI")


# ============================================================
# MONGODB
# ============================================================

client = MongoClient(
    MONGO_URI,
    connectTimeoutMS=30000
)

db = client["history"]

histories_collection = db["histories"]

logger.info("Connected to MongoDB Atlas successfully!")


# ============================================================
# NLTK RESOURCES
# ============================================================

def download_nltk_resources():

    resources = [
        "punkt",
        "averaged_perceptron_tagger"
    ]

    for resource in resources:

        try:

            nltk.download(
                resource,
                quiet=True
            )

        except Exception as e:

            logger.error(
                f"Error downloading {resource}: {e}"
            )


download_nltk_resources()


# ============================================================
# SPACY
# ============================================================

try:

    nlp = spacy.load(
        "en_core_web_sm"
    )

except Exception as e:

    logger.error(
        "Error loading spaCy model. "
        "Run 'python -m spacy download en_core_web_sm' "
        "to download the model."
    )

    raise e


# ============================================================
# LIVE SIGN RECOGNIZER
# ============================================================
from sign_recognizer import ISLSignRecognizer


# ============================================================
# FLASK APP
# ============================================================

app = Flask(
    __name__,
    template_folder="templates"
)

CORS(app)


# ============================================================
# LIVE ISL SIGN RECOGNITION
# ============================================================

logger.info("=" * 70)
logger.info("INITIALIZING LIVE ISL SIGN RECOGNIZER")
logger.info("=" * 70)

sign_recognizer = ISLSignRecognizer()

logger.info("LIVE ISL SIGN RECOGNIZER READY")


# ============================================================
# SIGN WEBCAM STATE
# ============================================================

camera = None
camera_lock = threading.Lock()
camera_running = False

last_sign_result = {
    "prediction": "",
    "confidence": 0.0,
    "stable_prediction": "",
    "hand_count": 0,
    "model": "",
    "v5_prediction": "",
    "v5_confidence": 0.0,
    "ds_prediction": "",
    "ds_confidence": 0.0
}


# ============================================================
# SIGN CAMERA FUNCTIONS
# ============================================================

def open_camera():
    global camera
    global camera_running

    with camera_lock:
        if camera is not None and camera.isOpened():
            camera_running = True
            return True

        logger.info("Opening webcam...")

        camera = cv2.VideoCapture(0)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        if not camera.isOpened():
            logger.error("Could not open webcam")
            camera = None
            camera_running = False
            return False

        camera_running = True
        sign_recognizer.reset()

        logger.info("Webcam opened successfully")
        return True


def close_camera():
    global camera
    global camera_running

    with camera_lock:
        camera_running = False

        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass
            camera = None

        sign_recognizer.reset()
        logger.info("Webcam closed")


def generate_sign_frames():
    global camera
    global camera_running
    global last_sign_result

    if not open_camera():
        return

    while camera_running:
        with camera_lock:
            if camera is None or not camera.isOpened():
                break
            success, frame = camera.read()

        if not success:
            logger.warning("Failed to read webcam frame")
            time.sleep(0.05)
            continue

        try:
            result = sign_recognizer.process_frame(frame)
            annotated_frame = result["frame"]

            last_sign_result = {
                "prediction": result.get("prediction", "") or "",
                "confidence": float(result.get("confidence", 0.0)),
                "stable_prediction": result.get("stable_prediction", "") or "",
                "hand_count": int(result.get("hand_count", 0)),
                "model": result.get("model", "") or "",
                "v5_prediction": result.get("v5_prediction", "") or "",
                "v5_confidence": float(result.get("v5_confidence", 0.0)),
                "ds_prediction": result.get("ds_prediction", "") or "",
                "ds_confidence": float(result.get("ds_confidence", 0.0))
            }

            success, buffer = cv2.imencode(".jpg", annotated_frame)
            if not success:
                continue

            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )

        except Exception as e:
            logger.error(f"Error processing sign frame: {e}")
            time.sleep(0.05)


# ============================================================
# SIGN RECOGNITION API
# ============================================================

@app.route("/sign_video")
def sign_video():
    return Response(
        generate_sign_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/sign_start", methods=["POST"])
def sign_start():
    try:
        success = open_camera()
        if not success:
            return jsonify({
                "error": True,
                "message": "Could not open webcam"
            }), 500

        return jsonify({
            "error": False,
            "message": "Sign recognition started"
        }), 200

    except Exception as e:
        logger.error(f"Error starting sign recognition: {e}")
        return jsonify({
            "error": True,
            "message": "Could not start sign recognition"
        }), 500


@app.route("/sign_stop", methods=["POST"])
def sign_stop():
    try:
        close_camera()
        return jsonify({
            "error": False,
            "message": "Sign recognition stopped"
        }), 200

    except Exception as e:
        logger.error(f"Error stopping sign recognition: {e}")
        return jsonify({
            "error": True,
            "message": "Could not stop sign recognition"
        }), 500


@app.route("/sign_state", methods=["GET"])
def sign_state():
    return jsonify({
        "error": False,
        "running": camera_running,
        **last_sign_result
    })


@app.route("/sign_clear", methods=["POST"])
def sign_clear():
    global last_sign_result

    sign_recognizer.reset()

    last_sign_result = {
        "prediction": "",
        "confidence": 0.0,
        "stable_prediction": "",
        "hand_count": 0,
        "model": "",
        "v5_prediction": "",
        "v5_confidence": 0.0,
        "ds_prediction": "",
        "ds_confidence": 0.0
    }

    return jsonify({
        "error": False,
        "message": "Sign recognition cleared"
    }), 200


# ============================================================
# LIVE LETTER RECOGNITION
#
# The webcam recognition program will POST a stable
# recognized letter here.
#
# Example:
#
# {
#     "letter": "A",
#     "confidence": 0.87
# }
#
# The browser can then GET /api/letter
# to retrieve the latest recognized letter.
# ============================================================

latest_letter = {
    "letter": "",
    "confidence": 0.0
}


@app.route(
    "/api/letter",
    methods=["POST"]
)
def receive_letter():

    global latest_letter

    try:

        data = request.get_json()

        if not data or "letter" not in data:

            return jsonify({
                "error": True,
                "message": "No letter provided"
            }), 400


        letter = str(
            data.get("letter", "")
        ).strip().upper()


        confidence = float(
            data.get(
                "confidence",
                0.0
            )
        )


        # ----------------------------------------------------
        # Validate the recognition result
        #
        # We accept:
        # A-Z
        # 0-9
        # ----------------------------------------------------

        if len(letter) != 1:

            return jsonify({
                "error": True,
                "message": "Invalid letter"
            }), 400


        if not (
            letter.isalpha()
            or
            letter.isdigit()
        ):

            return jsonify({
                "error": True,
                "message": "Invalid letter"
            }), 400


        # ----------------------------------------------------
        # Store latest prediction
        # ----------------------------------------------------

        latest_letter = {
            "letter": letter,
            "confidence": confidence
        }


        logger.info(
            "Live recognition: %s (%.1f%%)",
            letter,
            confidence * 100
        )


        return jsonify({

            "error": False,

            "letter": letter,

            "confidence": confidence

        }), 200


    except Exception as e:

        logger.error(
            f"Error receiving letter: {e}"
        )

        return jsonify({

            "error": True,

            "message":
                "Server error receiving letter"

        }), 500


@app.route(
    "/api/letter",
    methods=["GET"]
)
def get_letter():

    return jsonify({

        "error": False,

        "letter":
            latest_letter["letter"],

        "confidence":
            latest_letter["confidence"]

    })


# ============================================================
# MAIN PAGES
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


@app.route("/about")
def about():

    return render_template(
        "about.html"
    )


@app.route("/contact")
def contact():

    return render_template(
        "contact.html"
    )


# ============================================================
# HISTORY
# ============================================================

@app.route(
    "/save_history",
    methods=["POST"]
)
def save_history():

    try:

        data = request.get_json()


        if (
            not data
            or
            "original_text" not in data
            or
            "isl_text" not in data
        ):

            return jsonify({
                "error":
                    "Missing required fields"
            }), 400


        history_entry = {

            "original_text":
                data["original_text"],

            "isl_text":
                data["isl_text"],

            "timestamp":
                datetime.utcnow()

        }


        result = histories_collection.insert_one(
            history_entry
        )


        return jsonify({

            "message":
                "History saved successfully",

            "id":
                str(result.inserted_id)

        }), 201


    except Exception as e:

        logger.error(
            f"Error saving history: {e}"
        )

        return jsonify({

            "error":
                "Server error saving history"

        }), 500


@app.route(
    "/get_history",
    methods=["GET"]
)
def get_history():

    try:

        entries = list(

            histories_collection
            .find()
            .sort(
                "timestamp",
                -1
            )
            .limit(100)

        )


        for entry in entries:

            entry["_id"] = str(
                entry["_id"]
            )


        return jsonify(
            entries
        ), 200


    except Exception as e:

        logger.error(
            f"Error fetching history: {e}"
        )

        return jsonify({

            "error":
                "Server error fetching history"

        }), 500


@app.route(
    "/delete_history/<string:entry_id>",
    methods=["DELETE"]
)
def delete_history(entry_id):

    try:

        result = histories_collection.delete_one({

            "_id":
                ObjectId(entry_id)

        })


        if result.deleted_count == 0:

            return jsonify({

                "error":
                    "Entry not found"

            }), 404


        return jsonify({

            "message":
                "Entry deleted successfully"

        }), 200


    except Exception as e:

        logger.error(
            f"Error deleting history entry: {e}"
        )

        return jsonify({

            "error":
                "Invalid entry ID"

        }), 400


@app.route(
    "/clear_history",
    methods=["DELETE"]
)
def clear_history():

    try:

        result = histories_collection.delete_many({})


        return jsonify({

            "message":
                "History cleared successfully",

            "deleted_count":
                result.deleted_count

        }), 200


    except Exception as e:

        logger.error(
            f"Error clearing history: {e}"
        )

        return jsonify({

            "error":
                "Server error clearing history"

        }), 500


# ============================================================
# ENGLISH CONTRACTIONS
# ============================================================

CONTRACTIONS = {

    "i'm": "i am",
    "you're": "you are",
    "he's": "he is",
    "she's": "she is",
    "it's": "it is",
    "we're": "we are",
    "they're": "they are",

    "i've": "i have",
    "you've": "you have",
    "we've": "we have",
    "they've": "they have",

    "i'll": "i will",
    "you'll": "you will",
    "he'll": "he will",
    "she'll": "she will",
    "we'll": "we will",
    "they'll": "they will",
    "it'll": "it will",

    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",

    "haven't": "have not",
    "hasn't": "has not",
    "hadn't": "had not",

    "won't": "will not",
    "wouldn't": "would not",

    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",

    "can't": "cannot",
    "couldn't": "could not",
    "shouldn't": "should not",

    "mightn't": "might not",
    "mustn't": "must not"
}


# ============================================================
# EXPAND CONTRACTIONS
# ============================================================

def expand_contractions(text):

    contractions_pattern = re.compile(

        r"\b("
        +
        "|".join(
            re.escape(k)
            for k in CONTRACTIONS.keys()
        )
        +
        r")\b",

        re.IGNORECASE

    )


    def replace(match):

        word = match.group(
            0
        ).lower()


        expanded = CONTRACTIONS.get(
            word,
            word
        )


        if match.group(0)[0].isupper():

            return expanded.capitalize()


        return expanded


    return contractions_pattern.sub(
        replace,
        text
    )


# ============================================================
# TEXT PREPROCESSING
# ============================================================

def preprocess_text(text):

    """
    Enhanced preprocessing for ISL conversion
    with contraction handling and time format preservation.
    """

    text = text.lower().strip()


    # Expand contractions

    text = expand_contractions(
        text
    )


    # --------------------------------------------------------
    # Convert time format
    #
    # Example:
    # 10:30 -> 10 30
    # 7:00  -> 7
    # --------------------------------------------------------

    text = re.sub(
        r"\b(\d{1,2}):00\b",
        r"\1",
        text
    )


    text = re.sub(
        r"\b(\d{1,2}):(\d{1,2})\b",
        r"\1 \2",
        text
    )


    # Remove non-alphanumeric characters
    # except spaces

    text = re.sub(
        r"[^\w\s]",
        "",
        text
    )


    return text


# ============================================================
# SPACY → ISL STRUCTURE
# ============================================================

def extract_isl_structure_spacy(text):

    """
    Converts each word in the input sentence to
    its base form and removes unnecessary words.

    Also identifies tense markers and preserves
    directional words.
    """

    doc = nlp(text)

    important_words = []

    tense_marker = ""


    # --------------------------------------------------------
    # Direction words that should not be lemmatized
    # --------------------------------------------------------

    keep_words = {

        "left",
        "right",
        "back",
        "straight",
        "forward",
        "up",
        "down",
        "near",
        "next",
        "beside",
        "in",
        "on",
        "under",
        "from",
        "to"

    }


    for token in doc:

        # ----------------------------------------------------
        # Preserve direction words
        # ----------------------------------------------------

        if token.text.lower() in keep_words:

            important_words.append(
                token.text.lower()
            )

            continue


        # ----------------------------------------------------
        # Remove auxiliary verbs
        # ----------------------------------------------------

        if (
            token.pos_ in ["AUX"]
            and
            token.lemma_
            in [
                "be",
                "do",
                "have",
                "will"
            ]
        ):

            if token.lemma_ == "will":

                tense_marker = "FUTURE"


            continue


        # ----------------------------------------------------
        # Remove determiners and prepositions
        # ----------------------------------------------------

        if token.pos_ in [
            "DET",
            "ADP"
        ]:

            continue


        # ----------------------------------------------------
        # Past tense
        # ----------------------------------------------------

        if token.tag_ in [
            "VBD",
            "VBN"
        ]:

            tense_marker = "PAST"

            important_words.append(
                token.lemma_
            )


        # ----------------------------------------------------
        # Present
        # ----------------------------------------------------

        elif token.tag_ in [
            "VBG",
            "VBZ",
            "VBP"
        ]:

            important_words.append(
                token.lemma_
            )


        # ----------------------------------------------------
        # Other words
        # ----------------------------------------------------

        else:

            important_words.append(
                token.lemma_
            )


    # --------------------------------------------------------
    # Add tense marker
    # --------------------------------------------------------

    if tense_marker:

        important_words.append(
            tense_marker
        )


    return (
        " ".join(
            important_words
        )
        if important_words
        else text
    )


# ============================================================
# TEXT → ISL API
# ============================================================

@app.route(
    "/save_text",
    methods=["POST"]
)
def save_text():

    try:

        data = request.get_json()


        if (
            not data
            or
            "text" not in data
        ):

            return jsonify({

                "isl_structure": "",

                "message":
                    "No data provided",

                "error": True

            }), 400


        text = data.get(
            "text",
            ""
        ).strip()


        if not text:

            return jsonify({

                "isl_structure": "",

                "message":
                    "No text provided",

                "error": True

            }), 400


        logger.info(
            f"Received text: {text}"
        )


        processed_text = preprocess_text(
            text
        )


        isl_structure = (
            extract_isl_structure_spacy(
                processed_text
            )
        )


        logger.debug(
            f"spaCy extraction: "
            f"{isl_structure}"
        )


        return jsonify({

            "isl_structure":
                isl_structure,

            "original_text":
                text,

            "message":
                "Text processed successfully",

            "error": False

        })


    except Exception as e:

        logger.error(
            f"Error in save_text: {e}"
        )


        return jsonify({

            "isl_structure": "",

            "message":
                "Server error occurred",

            "error": True

        }), 500


# ============================================================
# START FLASK
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )