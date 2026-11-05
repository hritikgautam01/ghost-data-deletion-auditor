"""
Identity Resolution Engine for Ghost Data Still Exists.

Resolves subject identities across current profiles (user_identities.csv),
historical changes (user_audit_log.csv), and request payloads.

Invariants:
- Conservative email normalization (lowercase, stripped).
- Historical emails, phones, and hashes traced with exact audit provenance.
- Anti-collision: Never merges distinct subjects solely because names or domains match.
- Ambiguity detection: Conflicting matches flag ambiguity instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

try:
    from code.src.data.loader import find_dataset_dir, load_user_audit_log, load_user_identities
    from code.src.data.models import DeletionRequestRecord, UserAuditLogRecord, UserIdentityRecord
except ImportError:
    from src.data.loader import find_dataset_dir, load_user_audit_log, load_user_identities
    from src.data.models import DeletionRequestRecord, UserAuditLogRecord, UserIdentityRecord


@dataclass
class SubjectIdentity:
    """Consolidated subject identity graph for a deletion audit subject."""
    primary_user_id: Optional[str] = None
    canonical_name: Optional[str] = None
    current_email: Optional[str] = None
    current_phone: Optional[str] = None
    current_email_hash: Optional[str] = None
    
    # Complete historical and current identifier sets
    all_emails: Set[str] = field(default_factory=set)
    all_phones: Set[str] = field(default_factory=set)
    all_email_hashes: Set[str] = field(default_factory=set)
    all_names: Set[str] = field(default_factory=set)
    
    # Provenance and audit metadata
    match_reason: str = ""
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    provenance_sources: List[str] = field(default_factory=list)

    def matches_identifier(self, id_type: str, value: Optional[str]) -> bool:
        """Checks if a given identifier matches any current or historical value."""
        if not value:
            return False
        val_clean = value.strip().lower()
        if id_type == "email":
            return val_clean in self.all_emails
        elif id_type == "phone":
            # Compare normalized digits
            val_digits = "".join(ch for ch in value if ch.isdigit())
            if not val_digits:
                return False
            for p in self.all_phones:
                p_digits = "".join(ch for ch in p if ch.isdigit())
                if p_digits and (p_digits == val_digits or p_digits.endswith(val_digits) or val_digits.endswith(p_digits)):
                    return True
            return False
        elif id_type == "email_hash":
            return val_clean in self.all_email_hashes
        elif id_type == "user_id":
            return self.primary_user_id is not None and self.primary_user_id.lower() == val_clean
        elif id_type == "name":
            return val_clean in {n.strip().lower() for n in self.all_names}
        return False


class IdentityResolver:
    """Index and resolver for user identities and audit history."""

    def __init__(
        self,
        identities: Optional[List[UserIdentityRecord]] = None,
        audit_records: Optional[List[UserAuditLogRecord]] = None,
        dataset_dir: Optional[Path | str] = None,
    ):
        base_dir = find_dataset_dir(dataset_dir)
        self.identities = identities if identities is not None else load_user_identities(base_dir)
        self.audit_records = audit_records if audit_records is not None else load_user_audit_log(base_dir)

        # Lookup structures
        self._by_user_id: Dict[str, UserIdentityRecord] = {}
        self._current_email_to_uid: Dict[str, str] = {}
        self._historical_email_to_uids: Dict[str, Set[str]] = {}
        self._phone_to_uid: Dict[str, str] = {}
        self._hash_to_uid: Dict[str, str] = {}
        self._audit_by_uid: Dict[str, List[UserAuditLogRecord]] = {}

        self._build_indexes()

    def _build_indexes(self) -> None:
        """Indexes user identities and historical changes."""
        for u in self.identities:
            uid = u.user_id
            self._by_user_id[uid] = u
            if u.normalized_email:
                self._current_email_to_uid[u.normalized_email] = uid
            if u.phone:
                self._phone_to_uid[u.phone.strip()] = uid
            if u.email_hash:
                self._hash_to_uid[u.email_hash.strip().lower()] = uid

        for a in self.audit_records:
            uid = a.user_id
            self._audit_by_uid.setdefault(uid, []).append(a)
            field = a.field_name.strip().lower()
            if field == "email":
                if a.old_value:
                    old_em = a.old_value.strip().lower()
                    self._historical_email_to_uids.setdefault(old_em, set()).add(uid)
                if a.new_value:
                    new_em = a.new_value.strip().lower()
                    self._historical_email_to_uids.setdefault(new_em, set()).add(uid)
            elif field == "email_hash":
                if a.old_value:
                    self._hash_to_uid[a.old_value.strip().lower()] = uid
                if a.new_value:
                    self._hash_to_uid[a.new_value.strip().lower()] = uid

    def resolve(self, request_or_email: DeletionRequestRecord | str) -> SubjectIdentity:
        """
        Resolves a SubjectIdentity from a DeletionRequest or email string.

        Checks:
        1. Exact match on current normalized email.
        2. Exact match on historical audit log email.
        3. Ambiguity handling if historical email mapped to multiple users.
        """
        if isinstance(request_or_email, str):
            email_val = request_or_email
        else:
            email_val = request_or_email.email

        norm_email = email_val.strip().lower()

        # Case 1: Matches current profile directly
        if norm_email in self._current_email_to_uid:
            uid = self._current_email_to_uid[norm_email]
            return self._build_subject_identity(uid, match_reason=f"exact_current_email:{norm_email}")

        # Case 2: Matches historical email in user_audit_log
        if norm_email in self._historical_email_to_uids:
            matching_uids = self._historical_email_to_uids[norm_email]
            if len(matching_uids) == 1:
                uid = next(iter(matching_uids))
                return self._build_subject_identity(uid, match_reason=f"historical_audit_email:{norm_email}")
            else:
                # Ambiguous match: multiple users had this email
                return SubjectIdentity(
                    current_email=norm_email,
                    all_emails={norm_email},
                    is_ambiguous=True,
                    ambiguity_reason=f"Historical email '{norm_email}' matches multiple user IDs: {sorted(list(matching_uids))}",
                    match_reason="ambiguous_historical_email",
                )

        # Case 3: Email not found in current profiles or audit logs
        return SubjectIdentity(
            current_email=norm_email,
            all_emails={norm_email},
            is_ambiguous=True,
            ambiguity_reason=f"Email '{norm_email}' not found in user identities or audit logs",
            match_reason="unresolved_email",
        )

    def _build_subject_identity(self, uid: str, match_reason: str) -> SubjectIdentity:
        """Assembles all current and historical attributes for a resolved user ID."""
        user_record = self._by_user_id.get(uid)
        
        all_emails: Set[str] = set()
        all_phones: Set[str] = set()
        all_hashes: Set[str] = set()
        all_names: Set[str] = set()
        sources: List[str] = [f"user_identities.csv:{uid}"]

        canonical_name = None
        current_email = None
        current_phone = None
        current_hash = None

        if user_record:
            canonical_name = user_record.name
            current_email = user_record.normalized_email
            current_phone = user_record.phone
            current_hash = user_record.email_hash

            if user_record.normalized_email:
                all_emails.add(user_record.normalized_email)
            if user_record.phone:
                all_phones.add(user_record.phone)
            if user_record.email_hash:
                all_hashes.add(user_record.email_hash.strip().lower())
            if user_record.name:
                all_names.add(user_record.name.strip())

        # Pull historical changes from audit log
        audit_events = self._audit_by_uid.get(uid, [])
        for a in audit_events:
            sources.append(f"user_audit_log.csv:{a.audit_id}")
            f = a.field_name.strip().lower()
            if f == "email":
                if a.old_value:
                    all_emails.add(a.old_value.strip().lower())
                if a.new_value:
                    all_emails.add(a.new_value.strip().lower())
            elif f == "phone":
                if a.old_value:
                    all_phones.add(a.old_value.strip())
                if a.new_value:
                    all_phones.add(a.new_value.strip())
            elif f == "email_hash":
                if a.old_value:
                    all_hashes.add(a.old_value.strip().lower())
                if a.new_value:
                    all_hashes.add(a.new_value.strip().lower())
            elif f == "name":
                if a.old_value:
                    all_names.add(a.old_value.strip())
                if a.new_value:
                    all_names.add(a.new_value.strip())

        return SubjectIdentity(
            primary_user_id=uid,
            canonical_name=canonical_name,
            current_email=current_email,
            current_phone=current_phone,
            current_email_hash=current_hash,
            all_emails=all_emails,
            all_phones=all_phones,
            all_email_hashes=all_hashes,
            all_names=all_names,
            match_reason=match_reason,
            is_ambiguous=False,
            provenance_sources=sources,
        )
