NEG_CUES = ["niega", "no presenta", "no refiere", "sin ", "ausencia de", "no hay "]

def is_negated(text: str) -> bool:
    s = " " + text.lower() + " "
    return any(cue in s for cue in NEG_CUES)