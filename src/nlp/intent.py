"""
Multilingual Request Intent Classifier for Ghost Data Still Exists.

Determines whether a natural-language request authorizes deletion of personal data
or represents a non-deletion request (access, export, rectification/update, marketing opt-out).

Non-deletion requests are classified as NOT_APPLICABLE (steps_json = []).
"""

from __future__ import annotations

import re
from typing import Optional


# Multilingual deletion indicator keywords / phrases
_DELETION_PATTERNS = [
    # English inflections
    r'\b(?:delet(?:e|ed|ing|ion|ions)?|eras(?:e|ed|ing|ure)?|remov(?:e|ed|ing|al|als)?|purg(?:e|ed|ing)?|wip(?:e|ed|ing)?|destroy)\b',
    r'\b(?:close|closed|closing|terminate|terminating)\s+(?:and\s+terminate\s+)?(?:my|this|the)?\s*account\b',
    r'\b(?:account|profile)\s+is\s+gone\b',
    r'\bright\s+to\s+be\s+forgotten\b',
    # Spanish
    r'\b(?:elimin(?:ar|aci[oó]n|en|e|o|ad[oa]s?)|borrar|borrado|suprimir|supresi[oó]n|cerrar\s+(?:mi|la)\s+cuenta|cancelar\s+(?:mi|la)\s+cuenta|quitar)\b',
    # French
    r'\b(?:suppression|supprimer|effacer|effacement|fermer\s+(?:mon|le)\s+compte|droit\s+[aà]\s+l\'oubli)\b',
    # Portuguese
    r'\b(?:excluir|exclus[aã]o|apagar|eliminar|deletar|fechar\s+(?:minha|a)\s+cuenta|fechar\s+(?:minha|a)\s+conta)\b',
    # German
    r'\b(?:l[oö]schen|l[oö]schung|entfernen|entfernung|konto\s+schlie[ßs]en|vergessenwerden)\b',
    # Japanese
    r'(?:削除|消去|抹消|アカウント.*閉鎖|退会|消して)',
    # Korean
    r'(?:삭제|파기|제거|탈퇴|계정.*폐쇄)',
]

# Explicit non-deletion indicators (access, export, rectification/update, marketing opt-out)
_NON_DELETION_PATTERNS = [
    r'not\s+(?:asking\s+for|a\s+request\s+for)\s+(?:account\s+)?(?:deletion|erasure|delete)',
    r'(?:don\'t|do\s+not)\s+(?:delete|close|remove)',
    r'leave\s+(?:the\s+account|my\s+profile|my\s+records)\s+(?:active|as\s+it\s+is|in\s+place)',
    r'keep\s+the\s+account\s+as\s+it\s+is',
    r'continue\s+using\s+the\s+service',
    r'correct\s+it\s+without\s+removing',
    r'remove\s+me\s+from\s+marketing\s+lists\s+only',
    r'stop\s+the\s+promotional\s+emails',
    r'resetting\s+the\s+login',
    r'information\s+request,\s+not\s+a\s+request',
    r'send\s+me\s+a\s+copy.*don\'t\s+delete',
    r'download\s+my\s+account\s+information.*keep',
    r'mobile\s+number.*replace\s+it.*leave\s+the\s+account',
    r'change\s+the\s+email\s+address.*continue\s+using',
    r'\b(?:access\s+request|subject\s+access|export\s+only|copy\s+of\s+my\s+data|download\s+my\s+data|rectify|rectification|update\s+my|correct\s+my|marketing\s+opt-out|unsubscribe|newsletter)\b',
]

_DELETION_REGEX = re.compile('|'.join(_DELETION_PATTERNS), re.IGNORECASE)
_NON_DELETION_REGEX = re.compile('|'.join(_NON_DELETION_PATTERNS), re.IGNORECASE)


class IntentClassifier:
    """Classifies deletion request text across supported languages."""

    @staticmethod
    def is_deletion_request(request_text: Optional[str]) -> bool:
        """
        Returns True if the request authorizes deletion/erasure/account closure.
        Returns False if the request is strictly non-deletion (e.g. access, correction, export only).
        """
        if not request_text or not request_text.strip():
            return False

        text = request_text.strip()

        # Check explicit non-deletion patterns
        if _NON_DELETION_REGEX.search(text):
            return False

        return bool(_DELETION_REGEX.search(text))
