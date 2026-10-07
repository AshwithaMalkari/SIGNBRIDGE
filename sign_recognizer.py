import cv2
import mediapipe as mp
import numpy as np
import tensorflow as tf

from collections import deque, Counter
from pathlib import Path


# ============================================================
# ISL SIGN RECOGNIZER
#
# Reusable version of the working webcam recognizer.
#
# V4 SINGLE-HAND
# V5 TWO-HAND
# D/S TARGETED CORRECTION
#
# This file DOES NOT open a webcam by itself.
# Flask will provide webcam frames to process_frame().
# ============================================================


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# MODEL FILES
# ============================================================

SINGLE_MODEL_FILE = (
    PROJECT_ROOT / "isl_landmark_model_v4.keras"
)

SINGLE_CLASS_FILE = (
    PROJECT_ROOT / "isl_landmark_classes_v4.txt"
)

TWO_MODEL_FILE = (
    PROJECT_ROOT / "isl_twohand_model_v5.keras"
)

TWO_CLASS_FILE = (
    PROJECT_ROOT / "isl_twohand_classes_v5.txt"
)

DS_CORRECTION_MODEL_FILE = (
    PROJECT_ROOT / "isl_ds_correction_v8.keras"
)

DS_CORRECTION_CLASS_FILE = (
    PROJECT_ROOT / "isl_ds_correction_classes_v8.txt"
)


# ============================================================
# EXPECTED CLASSES
# ============================================================

SINGLE_HAND_CLASSES = [
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "C",
    "I",
    "L",
    "O",
    "U",
    "V"
]


TWO_HAND_CLASSES = [
    "A",
    "B",
    "D",
    "E",
    "F",
    "G",
    "H",
    "J",
    "K",
    "M",
    "N",
    "P",
    "Q",
    "R",
    "S",
    "T",
    "W",
    "X",
    "Y",
    "Z"
]


# ============================================================
# SETTINGS
# ============================================================

MIN_DETECTION_CONFIDENCE = 0.60
MIN_TRACKING_CONFIDENCE = 0.60

SMOOTHING_WINDOW = 12
CONFIDENCE_THRESHOLD = 0.50

DS_CORRECTION_THRESHOLD = 0.90
DS_STABLE_WINDOW = 8

DS_TRIGGER_CLASSES = {
    "P",
    "H",
    "Q",
    "J",
    "E",
    "Z"
}


# ============================================================
# CLASS LOADING
# ============================================================

def load_classes(filename):

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as f:

        return [
            line.strip()
            for line in f
            if line.strip()
        ]


# ============================================================
# RECOGNIZER CLASS
# ============================================================

class ISLSignRecognizer:

    def __init__(self):

        print()
        print("=" * 70)
        print("LOADING ISL SIGN RECOGNIZER")
        print("=" * 70)

        # ----------------------------------------------------
        # LOAD MODELS
        # ----------------------------------------------------

        print()
        print("Loading single-hand V4 model...")

        self.single_model = (
            tf.keras.models.load_model(
                SINGLE_MODEL_FILE,
                compile=False
            )
        )

        print("Loading two-hand V5 model...")

        self.two_model = (
            tf.keras.models.load_model(
                TWO_MODEL_FILE,
                compile=False
            )
        )

        print("Loading D/S correction model...")

        self.ds_correction_model = (
            tf.keras.models.load_model(
                DS_CORRECTION_MODEL_FILE,
                compile=False
            )
        )

        # ----------------------------------------------------
        # LOAD CLASS FILES
        # ----------------------------------------------------

        self.single_classes = load_classes(
            SINGLE_CLASS_FILE
        )

        self.two_classes = load_classes(
            TWO_CLASS_FILE
        )

        self.ds_correction_classes = load_classes(
            DS_CORRECTION_CLASS_FILE
        )

        # ----------------------------------------------------
        # SAFETY CHECKS
        # ----------------------------------------------------

        missing_single = [
            c
            for c in SINGLE_HAND_CLASSES
            if c not in self.single_classes
        ]

        missing_two = [
            c
            for c in TWO_HAND_CLASSES
            if c not in self.two_classes
        ]

        if missing_single:

            raise RuntimeError(
                "Missing single-hand classes: "
                + str(missing_single)
            )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # D and S are NOT expected inside V5.
        #
        # They are handled by the dedicated
        # D/S correction model.
        # ----------------------------------------------------

        missing_two_without_ds = [
            c
            for c in missing_two
            if c not in ["D", "S"]
        ]

        if missing_two_without_ds:

            raise RuntimeError(
                "Missing two-hand classes: "
                + str(missing_two_without_ds)
            )

        # ----------------------------------------------------
        # CHECK D/S CORRECTION MODEL
        # ----------------------------------------------------

        missing_ds = [
            c
            for c in ["D", "S"]
            if c not in self.ds_correction_classes
        ]

        if missing_ds:

            raise RuntimeError(
                "D/S correction model is missing: "
                + str(missing_ds)
            )

        # ----------------------------------------------------
        # MEDIAPIPE
        # ----------------------------------------------------

        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils

        self.hands_detector = (
            self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                model_complexity=1,
                min_detection_confidence=(
                    MIN_DETECTION_CONFIDENCE
                ),
                min_tracking_confidence=(
                    MIN_TRACKING_CONFIDENCE
                )
            )
        )

        # ----------------------------------------------------
        # SMOOTHING
        # ----------------------------------------------------

        self.prediction_history = deque(
            maxlen=SMOOTHING_WINDOW
        )

        self.ds_history = deque(
            maxlen=DS_STABLE_WINDOW
        )

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        self.last_prediction = None
        self.last_confidence = 0.0
        self.last_model = "WAITING"

        print()
        print("Single-hand classes:")
        print(self.single_classes)

        print()
        print("Two-hand V5 classes:")
        print(self.two_classes)

        print()
        print("D/S correction classes:")
        print(self.ds_correction_classes)

        print()
        print("Single model input:")
        print(self.single_model.input_shape)

        print("Two-hand model input:")
        print(self.two_model.input_shape)

        print("D/S model input:")
        print(self.ds_correction_model.input_shape)

        print()
        print("ISL SIGN RECOGNIZER READY")
        print("=" * 70)


    # ========================================================
    # FEATURE EXTRACTION
    # ========================================================

    def extract_hand_features(self, hand):

        wrist = hand.landmark[0]

        features = []

        for landmark in hand.landmark:

            features.extend([
                landmark.x - wrist.x,
                landmark.y - wrist.y,
                landmark.z - wrist.z
            ])

        return features


    # ========================================================
    # NORMALIZATION
    #
    # ONLY USED BY SINGLE-HAND V4
    # ========================================================

    def normalize_features(self, features):

        x = np.asarray(
            features,
            dtype=np.float32
        )

        norm = np.linalg.norm(x)

        if norm > 1e-6:

            x = x / norm

        return x


    # ========================================================
    # LEFT / RIGHT HAND
    # ========================================================

    def get_left_right_hands(
        self,
        hand_landmarks,
        handedness
    ):

        left_hand = None
        right_hand = None

        for hand, classification in zip(
            hand_landmarks,
            handedness
        ):

            label = (
                classification
                .classification[0]
                .label
            )

            if label == "Left":

                left_hand = hand

            elif label == "Right":

                right_hand = hand

        return (
            left_hand,
            right_hand
        )


    # ========================================================
    # TWO-HAND FEATURES
    #
    # EXACT V5 FORMAT:
    #
    # LEFT  = 63
    # RIGHT = 63
    # TOTAL = 126
    #
    # NO NORMALIZATION
    # ========================================================

    def extract_two_hand_features(
        self,
        left_hand,
        right_hand
    ):

        left_features = (
            self.extract_hand_features(
                left_hand
            )
        )

        right_features = (
            self.extract_hand_features(
                right_hand
            )
        )

        return (
            left_features
            +
            right_features
        )


    # ========================================================
    # SINGLE-HAND V4 PREDICTION
    # ========================================================

    def predict_single_hand(
        self,
        hand
    ):

        features = (
            self.extract_hand_features(
                hand
            )
        )

        if len(features) != 63:

            return None, 0.0

        # V4 uses normalization.

        features = (
            self.normalize_features(
                features
            )
        )

        x = features.reshape(
            1,
            63
        )

        probabilities = (
            self.single_model.predict(
                x,
                verbose=0
            )[0]
        )

        index = int(
            np.argmax(probabilities)
        )

        prediction = (
            self.single_classes[index]
        )

        confidence = float(
            probabilities[index]
        )

        return (
            prediction,
            confidence
        )


    # ========================================================
    # TWO-HAND V5 PREDICTION
    # ========================================================

    def predict_two_hands(
        self,
        left_hand,
        right_hand
    ):

        features = (
            self.extract_two_hand_features(
                left_hand,
                right_hand
            )
        )

        if len(features) != 126:

            return None, 0.0

        # IMPORTANT:
        #
        # V5 expects RAW wrist-relative
        # 126 features.
        #
        # DO NOT NORMALIZE.

        x = np.asarray(
            features,
            dtype=np.float32
        ).reshape(
            1,
            126
        )

        probabilities = (
            self.two_model.predict(
                x,
                verbose=0
            )[0]
        )

        index = int(
            np.argmax(probabilities)
        )

        prediction = (
            self.two_classes[index]
        )

        confidence = float(
            probabilities[index]
        )

        return (
            prediction,
            confidence
        )


    # ========================================================
    # D/S CORRECTION
    # ========================================================

    def predict_ds_correction(
        self,
        left_hand,
        right_hand
    ):

        features = (
            self.extract_two_hand_features(
                left_hand,
                right_hand
            )
        )

        if len(features) != 126:

            return None, 0.0

        # IMPORTANT:
        #
        # D/S model expects RAW 126 features.
        # NO NORMALIZATION.

        x = np.asarray(
            features,
            dtype=np.float32
        ).reshape(
            1,
            126
        )

        probabilities = (
            self.ds_correction_model.predict(
                x,
                verbose=0
            )[0]
        )

        index = int(
            np.argmax(probabilities)
        )

        prediction = (
            self.ds_correction_classes[index]
        )

        confidence = float(
            probabilities[index]
        )

        return (
            prediction,
            confidence
        )


    # ========================================================
    # GENERAL STABLE PREDICTION
    # ========================================================

    def get_stable_prediction(self):

        if not self.prediction_history:

            return None

        counts = Counter(
            self.prediction_history
        )

        return (
            counts.most_common(1)[0][0]
        )


    # ========================================================
    # D/S STABLE PREDICTION
    # ========================================================

    def get_stable_ds_prediction(self):

        if (
            len(self.ds_history)
            <
            DS_STABLE_WINDOW
        ):

            return None

        counts = Counter(
            self.ds_history
        )

        prediction, count = (
            counts.most_common(1)[0]
        )

        if count >= DS_STABLE_WINDOW:

            return prediction

        return None


    # ========================================================
    # PROCESS ONE FRAME
    # ========================================================

    def process_frame(
        self,
        frame
    ):

        # ----------------------------------------------------
        # MIRROR IMAGE
        # ----------------------------------------------------

        frame = cv2.flip(
            frame,
            1
        )

        # ----------------------------------------------------
        # RGB
        # ----------------------------------------------------

        rgb = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        # ----------------------------------------------------
        # MEDIAPIPE
        # ----------------------------------------------------

        result = (
            self.hands_detector.process(
                rgb
            )
        )

        hand_landmarks = (
            result.multi_hand_landmarks
            if result.multi_hand_landmarks
            else []
        )

        handedness = (
            result.multi_handedness
            if result.multi_handedness
            else []
        )

        hand_count = len(
            hand_landmarks
        )

        # ----------------------------------------------------
        # DRAW LANDMARKS
        # ----------------------------------------------------

        for hand in hand_landmarks:

            self.mp_draw.draw_landmarks(
                frame,
                hand,
                self.mp_hands.HAND_CONNECTIONS
            )

        # ----------------------------------------------------
        # DEFAULT VALUES
        # ----------------------------------------------------

        current_prediction = None
        current_confidence = 0.0

        model_used = "WAITING"

        v5_prediction = None
        v5_confidence = 0.0

        ds_prediction = None
        ds_confidence = 0.0

        # ====================================================
        # ONE HAND
        # ====================================================

        if hand_count == 1:

            (
                current_prediction,
                current_confidence
            ) = self.predict_single_hand(
                hand_landmarks[0]
            )

            model_used = "SINGLE V4"

            self.ds_history.clear()

        # ====================================================
        # TWO HANDS
        # ====================================================

        elif hand_count == 2:

            (
                left_hand,
                right_hand
            ) = self.get_left_right_hands(
                hand_landmarks,
                handedness
            )

            if (
                left_hand is not None
                and
                right_hand is not None
            ):

                # ------------------------------------------------
                # STEP 1
                # V5 MAIN MODEL
                # ------------------------------------------------

                (
                    v5_prediction,
                    v5_confidence
                ) = self.predict_two_hands(
                    left_hand,
                    right_hand
                )

                # ------------------------------------------------
                # STEP 2
                # D/S CORRECTION
                # ------------------------------------------------

                if (
                    v5_prediction
                    in
                    DS_TRIGGER_CLASSES
                ):

                    (
                        ds_prediction,
                        ds_confidence
                    ) = self.predict_ds_correction(
                        left_hand,
                        right_hand
                    )

                    if (
                        ds_prediction
                        in ["D", "S"]
                        and
                        ds_confidence
                        >=
                        DS_CORRECTION_THRESHOLD
                    ):

                        self.ds_history.append(
                            ds_prediction
                        )

                    else:

                        self.ds_history.clear()

                else:

                    self.ds_history.clear()

                # ------------------------------------------------
                # STEP 3
                # SELECT FINAL RESULT
                # ------------------------------------------------

                stable_ds = (
                    self.get_stable_ds_prediction()
                )

                if stable_ds is not None:

                    current_prediction = (
                        stable_ds
                    )

                    current_confidence = (
                        ds_confidence
                    )

                    model_used = (
                        "D/S CORRECTION"
                    )

                else:

                    current_prediction = (
                        v5_prediction
                    )

                    current_confidence = (
                        v5_confidence
                    )

                    model_used = (
                        "TWO-HAND V5"
                    )

            else:

                current_prediction = None
                current_confidence = 0.0

                model_used = (
                    "TWO-HAND / UNKNOWN"
                )

                self.ds_history.clear()

        # ====================================================
        # NO HAND
        # ====================================================

        else:

            current_prediction = None
            current_confidence = 0.0

            model_used = "WAITING"

            self.prediction_history.clear()
            self.ds_history.clear()

        # ====================================================
        # GENERAL SMOOTHING
        # ====================================================

        if (
            current_prediction is not None
            and
            current_confidence
            >=
            CONFIDENCE_THRESHOLD
        ):

            self.prediction_history.append(
                current_prediction
            )

        elif hand_count == 0:

            self.prediction_history.clear()

        # ====================================================
        # STABLE PREDICTION
        # ====================================================

        stable_prediction = (
            self.get_stable_prediction()
        )

        # ====================================================
        # SAVE STATE
        # ====================================================

        self.last_prediction = (
            current_prediction
        )

        self.last_confidence = (
            current_confidence
        )

        self.last_model = (
            model_used
        )

        # ====================================================
        # DRAW STATUS
        # ====================================================

        cv2.putText(
            frame,
            f"Hands detected: {hand_count}",
            (25, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (0, 255, 255),
            2
        )

        cv2.putText(
            frame,
            f"Model: {model_used}",
            (25, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2
        )

        # ----------------------------------------------------
        # V5 DISPLAY
        # ----------------------------------------------------

        if (
            hand_count == 2
            and
            v5_prediction
        ):

            cv2.putText(
                frame,
                (
                    f"V5: {v5_prediction} "
                    f"({v5_confidence * 100:.1f}%)"
                ),
                (25, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (200, 200, 255),
                2
            )

        # ----------------------------------------------------
        # D/S DISPLAY
        # ----------------------------------------------------

        if (
            hand_count == 2
            and
            ds_prediction is not None
        ):

            cv2.putText(
                frame,
                (
                    f"D/S: {ds_prediction} "
                    f"({ds_confidence * 100:.1f}%)"
                ),
                (25, 145),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 200, 100),
                2
            )

        # ----------------------------------------------------
        # CURRENT PREDICTION
        # ----------------------------------------------------

        if current_prediction is not None:

            cv2.putText(
                frame,
                f"Current: {current_prediction}",
                (25, 185),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                3
            )

            cv2.putText(
                frame,
                (
                    f"Confidence: "
                    f"{current_confidence * 100:.1f}%"
                ),
                (25, 225),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

        # ----------------------------------------------------
        # STABLE PREDICTION
        # ----------------------------------------------------

        if stable_prediction is not None:

            cv2.putText(
                frame,
                f"STABLE: {stable_prediction}",
                (25, 280),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (255, 255, 0),
                4
            )

        # ----------------------------------------------------
        # HAND STATUS
        # ----------------------------------------------------

        if hand_count == 0:

            status = "Show your hand"

        elif hand_count == 1:

            status = "Single-hand model active"

        else:

            status = "Two-hand model active"

        cv2.putText(
            frame,
            status,
            (25, 325),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2
        )

        # ====================================================
        # RETURN RESULT
        # ====================================================

        return {
            "frame": frame,
            "prediction": current_prediction,
            "confidence": current_confidence,
            "stable_prediction": stable_prediction,
            "hand_count": hand_count,
            "model": model_used,
            "v5_prediction": v5_prediction,
            "v5_confidence": v5_confidence,
            "ds_prediction": ds_prediction,
            "ds_confidence": ds_confidence
        }


    # ========================================================
    # RESET
    # ========================================================

    def reset(self):

        self.prediction_history.clear()

        self.ds_history.clear()

        self.last_prediction = None

        self.last_confidence = 0.0

        self.last_model = "WAITING"


    # ========================================================
    # CLOSE
    # ========================================================

    def close(self):

        if self.hands_detector is not None:

            self.hands_detector.close()