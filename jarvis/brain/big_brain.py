"""
JARVIS AI — Big Brain (Mission Memory & Knowledge Retrieval Engine)
===================================================================
100% Factual and Deterministic Memory Storage.

Key intelligence features:
  - Step-aware procedure navigation: "what do I do after X?" → returns the correct next step
  - Direct step lookup: "step 4?" → returns step 4 precisely
  - Keyword-based step matching: finds the most relevant single step, not the full document
  - YAML / JSON / Markdown / TXT knowledge ingestion
"""

import re
import yaml
import json
from pathlib import Path
from loguru import logger
from typing import Optional, Dict, Any, List


STOP_WORDS = {
    "give", "me", "the", "for", "with", "what", "how", "is", "are", "my", "and",
    "of", "in", "to", "a", "an", "do", "i", "should", "need", "must", "can",
    "donne", "moi", "le", "la", "les", "du", "de", "est", "un", "une", "faire",
    "dois", "faut", "apres", "avant", "step", "etape", "after", "before", "next",
    "then", "following", "complete", "completed", "done", "finish", "now", "please",
    "that", "this", "think", "going", "doing", "beautiful", "good", "well", "really",
    "would", "could", "like", "want", "know", "say", "said", "tell", "told", "thing",
    "things", "will", "make", "see", "look", "come", "go", "take", "get", "put", "have",
    "has", "had", "been", "was", "were", "be", "being", "been", "also", "just", "very"
}

# "What comes NEXT after [topic]?" or "next" / "done" / "ready" / "yes" / "ok"
NEXT_STEP_PATTERNS = re.compile(
    r"\b(after|next|following|then|what.*next|qu.*apres|ensuite|suivant|and\s+then|done|ready|completed|finished|yes|oui|ok|okay|continuer|c'est\s+fait)\b",
    re.IGNORECASE,
)
# "Go BACK" / "previous"
PREV_STEP_PATTERNS = re.compile(
    r"\b(previous|before|back|prior|last|redo|go\s+back|precedent|précédent)\b",
    re.IGNORECASE,
)
# "REPEAT" / "again"
REPEAT_PATTERNS = re.compile(
    r"\b(repeat|again|once\s+more|say\s+again|répète|encore)\b",
    re.IGNORECASE,
)

# Pattern: "step N" or "étape N"
STEP_NUMBER_PATTERN = re.compile(r"\b(?:step|etape|étape)\s+(\d+)\b", re.IGNORECASE)


def _stem(word: str) -> str:
    """Minimal English suffix stripper for fuzzy keyword matching."""
    for suffix in ("ing", "tion", "ation", "ment", "ness", "ers", "ed", "er", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


class ProcedureNavigator:
    """
    Parses a procedure document into individual numbered steps and enables
    intelligent navigation: find step by keyword, get next step, get by number,
    and sub-section / category jumping.
    """

    def __init__(self, doc_name: str, sections: List[Dict[str, Any]]):
        self.doc_name = doc_name
        self.steps, self.phases = self._extract_steps_and_phases(sections)

    def _extract_steps_and_phases(self, sections: List[Dict[str, Any]]) -> tuple[List[Dict], Dict[str, List[Dict]]]:
        """Extract all numbered steps anchored strictly at line beginnings."""
        steps = []
        phases: Dict[str, List[Dict]] = {}

        for sec in sections:
            phase = sec["heading"]
            lines = sec.get("raw_lines", [])

            phase_steps = []
            for line in lines:
                m = re.match(r'^\s*[-*]?\s*Step\s+(\d+)\s*[:\-]\s*(.*)', line, re.IGNORECASE)
                if not m:
                    continue

                num = int(m.group(1))
                raw_desc = m.group(2).strip()

                dur_match = re.search(r'\(Duration:\s*([^)]+)\)', raw_desc, re.IGNORECASE)
                duration = dur_match.group(1).strip() if dur_match else None
                clean_desc = re.sub(r'\(Duration:[^)]+\)', '', raw_desc).strip().rstrip(" .-")

                is_decision = bool(re.search(r'decision\s+point|if\s+yes|if\s+no', clean_desc, re.IGNORECASE))

                if clean_desc:
                    step_obj = {
                        "number": num,
                        "phase": phase,
                        "doc_name": self.doc_name,
                        "text": clean_desc,
                        "duration": duration,
                        "is_decision": is_decision,
                        "keywords": set(re.findall(r"\b[a-z]{3,}\b", clean_desc.lower())),
                    }
                    steps.append(step_obj)
                    phase_steps.append(step_obj)

            if phase_steps:
                phases[phase] = phase_steps

        return steps, phases

    def find_best_step(self, keywords: List[str], min_score: float = 3.5) -> Optional[Dict]:
        """
        Return the step best matching the keywords using IDF-style rare-word weighting.
        """
        if not self.steps or not keywords:
            return None

        import math
        total_steps = len(self.steps)
        word_doc_freq: Dict[str, int] = {}
        for step in self.steps:
            for w in {_stem(k) for k in step["keywords"]}:
                word_doc_freq[w] = word_doc_freq.get(w, 0) + 1

        def idf(stem: str) -> float:
            df = word_doc_freq.get(stem, 0)
            if df == 0:
                return 0.0
            return math.log((total_steps + 1) / (df + 1)) + 1.0

        kw_stems = {_stem(w): idf(_stem(w)) for w in keywords}

        best, best_score = None, 0.0
        for step in self.steps:
            step_stems = {_stem(w) for w in step["keywords"]}
            score = sum(weight for stem, weight in kw_stems.items() if stem in step_stems)
            if score > best_score:
                best_score, best = score, step

        if best_score >= min_score:
            return best
        return None

    def get_by_number(self, n: int, phase: Optional[str] = None) -> Optional[Dict]:
        candidates = [s for s in self.steps if s["number"] == n]
        if not candidates:
            return None
        if phase:
            for s in candidates:
                if phase.lower() in s["phase"].lower():
                    return s
        return candidates[0]

    def get_all_by_number(self, n: int) -> List[Dict]:
        """Return all steps in this procedure document matching step number n."""
        return [s for s in self.steps if s["number"] == n]

    def get_first_step_of_phase(self, phase_name: str) -> Optional[Dict]:
        """Return the first step in a specific sub-section/phase."""
        phase_steps = self.phases.get(phase_name)
        if phase_steps:
            return phase_steps[0]
        # Match by partial string
        for p, s_list in self.phases.items():
            if phase_name.lower() in p.lower() or p.lower() in phase_name.lower():
                return s_list[0]
        return None

    def next_step_after(self, step: Dict) -> Optional[Dict]:
        """Return next step in procedure, setting section transition flag if phase changes."""
        for idx, s in enumerate(self.steps):
            if s is step or (s["number"] == step["number"] and s["phase"] == step["phase"]):
                if idx + 1 < len(self.steps):
                    nxt = dict(self.steps[idx + 1])
                    if nxt["phase"] != step["phase"]:
                        nxt["is_section_transition"] = True
                        nxt["prev_phase"] = step["phase"]
                    return nxt
                break
        return None

    def format_step(self, step: Dict) -> str:
        """
        Rule 3 — Concise response format: ONLY action, important notes, and duration.
        Includes sub-section completion notification when transitioning sections.
        """
        dur = f" (Duration: {step['duration']})" if step.get("duration") else ""
        if step.get("is_section_transition"):
            return f"{step['prev_phase']} is completed. Next section is {step['phase']}: Step {step['number']} — {step['text']}{dur}."
        return f"Step {step['number']} — {step['phase']}: {step['text']}{dur}."


class BigBrain:
    """
    Mission Knowledge Engine (Big Brain).
    Stores structured facts, manuals, and procedures.
    Enforces operational rules: ambiguity resolution, sub-section jumping,
    concise responses, and state decision checkpoints.
    """

    def __init__(self, knowledge_dir: str = "data/knowledge_base/"):
        self.knowledge_dir = Path(knowledge_dir)
        self.kb_data: Dict[str, Any] = {}
        self.text_documents: Dict[str, List[Dict]] = {}
        self.procedure_navigators: Dict[str, ProcedureNavigator] = {}

        # ── Session state ──────────────────────────────────────────────────────
        self._current_procedure: Optional[str] = None     # active procedure key
        self._last_step: Optional[Dict] = None             # last step returned
        self._pending_decision: Optional[Dict] = None      # active decision point waiting for YES/NO
        self._pending_clarification: Optional[Dict] = None # active clarification waiting for proc/section name
        self.load_knowledge_base()

    # ── Loading ────────────────────────────────────────────────────────────────

    def load_knowledge_base(self) -> None:
        if not self.knowledge_dir.exists():
            logger.warning(f"[BIG BRAIN] Knowledge dir not found. Creating: {self.knowledge_dir}")
            self.knowledge_dir.mkdir(parents=True, exist_ok=True)
            return

        loaded = 0

        # 1. Structured YAML / JSON
        for fp in (list(self.knowledge_dir.glob("*.yaml"))
                   + list(self.knowledge_dir.glob("*.yml"))
                   + list(self.knowledge_dir.glob("*.json"))):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    content = json.load(f) if fp.suffix == ".json" else yaml.safe_load(f)
                if content and isinstance(content, dict):
                    self.kb_data[fp.stem] = content
                    loaded += 1
            except Exception as e:
                logger.error(f"[BIG BRAIN] Error loading '{fp.name}': {e}")

        # 2. Markdown / TXT procedure documents
        for fp in list(self.knowledge_dir.glob("*.md")) + list(self.knowledge_dir.glob("*.txt")):
            try:
                sections = self._parse_text_document(fp)
                if sections:
                    self.text_documents[fp.stem] = sections
                    nav = ProcedureNavigator(fp.stem, sections)
                    if nav.steps:
                        self.procedure_navigators[fp.stem] = nav
                        logger.debug(f"[BIG BRAIN] Indexed {len(nav.steps)} steps from '{fp.name}'")
                    loaded += 1
            except Exception as e:
                logger.error(f"[BIG BRAIN] Error parsing '{fp.name}': {e}")

        logger.success(f"[BIG BRAIN] Loaded {loaded} documents, "
                       f"{len(self.procedure_navigators)} navigable procedures.")

    def _parse_text_document(self, file_path: Path) -> List[Dict[str, Any]]:
        sections, current_heading = [], file_path.stem.replace("_", " ").title()
        current_lines: List[str] = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str.startswith("#"):
                    if current_lines:
                        sections.append({
                            "heading": current_heading,
                            "content": " ".join(current_lines),
                            "raw_lines": current_lines,
                        })
                        current_lines = []
                    current_heading = line_str.lstrip("#").strip()
                elif line_str:
                    current_lines.append(line_str)
        if current_lines:
            sections.append({
                "heading": current_heading,
                "content": " ".join(current_lines),
                "raw_lines": current_lines,
            })
        return sections

    @property
    def has_active_session(self) -> bool:
        """Returns True if user is currently navigating a procedure or resolving a clarification."""
        return (self._current_procedure is not None and self._last_step is not None) or (self._pending_clarification is not None)

    def get_active_session_info(self) -> Dict[str, Any]:
        """Return dict with title, step number, and text of active procedure step."""
        title = self._current_procedure.replace("_procedure", "").replace("_", " ").title() if self._current_procedure else "AOUDA Standby"
        step = self._last_step["number"] if self._last_step and isinstance(self._last_step, dict) else 0
        desc = self._last_step["text"] if self._last_step and isinstance(self._last_step, dict) else "Say 'AOUDA' to initiate voice session."
        return {"title": title, "step": step, "instruction": desc}

    def cancel_active_procedure(self) -> None:
        self._current_procedure = None
        self._last_step = None
        self._pending_decision = None
        self._pending_clarification = None

    # ── Main query entry point ─────────────────────────────────────────────────

    def query(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            return None
        t = text.lower().strip()

        # Cancel / Exit active procedure
        if any(kw in t for kw in ["cancel", "stop procedure", "exit procedure", "annuler", "quitter", "stop", "arrêt"]):
            if self.has_active_session:
                self.cancel_active_procedure()
                return "Procedure cancelled. AOUDA returning to standby mode."

        # Handle Pending Clarification Answer (e.g. "Caillou", "Sample Return", "Laser targeting", "Pre-EVA")
        if self._pending_clarification:
            matches = self._pending_clarification.get("matches", [])
            selected = None

            for doc_title, phase_name, nav, step in matches:
                doc_words = [w for w in re.split(r'[_\s]+', doc_title.lower()) if len(w) >= 4]
                phase_words = [w for w in re.split(r'[_\s]+', phase_name.lower()) if len(w) >= 4 and w not in STOP_WORDS]
                if any(w in t for w in doc_words + phase_words + ["target", "targeting", "ciblage", "laser", "eva", "prep"]):
                    selected = (nav, step)
                    break

            if not selected and matches:
                # Default to first match if input was ambiguous
                selected = (matches[0][2], matches[0][3])

            if selected:
                nav, step = selected
                self._pending_clarification = None
                self._current_procedure = nav.doc_name
                self._last_step = step
                return self._format_step_response(nav, step)

        # Rule 4: Handle Pending Decision Checkpoint (YES / NO response)
        if self._pending_decision:
            is_yes = any(kw in t for kw in ["yes", "oui", "yep", "affirmative", "si", "correct", "encore", "again"])
            is_no  = any(kw in t for kw in ["no", "non", "nope", "negative", "terminé", "done", "finish", "complete"])
            if is_yes or is_no:
                doc_name = self._pending_decision["doc"]
                nav = self.procedure_navigators.get(doc_name)
                self._pending_decision = None
                if nav:
                    if is_yes:
                        # Return to Step 4 (Laser Targeting Procedure)
                        step_4 = nav.get_by_number(4, phase="Targeting")
                        if step_4:
                            self._last_step = step_4
                            return f"Returning to targeting: {nav.format_step(step_4)}"
                    else:
                        # Proceed to Step 11 (End of EVA Procedure)
                        step_11 = nav.get_by_number(11)
                        if step_11:
                            self._last_step = step_11
                            return f"Proceeding to End of EVA: {nav.format_step(step_11)}"

        # 1. EVA Checklists (structured YAML)
        if any(kw in t for kw in ["checklist", "pre eva", "egress", "post eva"]):
            checklists = self.kb_data.get("eva_procedures", {}).get("checklists", {})
            if any(kw in t for kw in ["post", "egress", "return", "retour", "fin"]):
                post = checklists.get("post_eva", {})
                steps = " → ".join(post.get("steps", []))
                return f"{post.get('title', 'Post-EVA')}: {steps}"
            pre = checklists.get("pre_eva", {})
            steps = " → ".join(pre.get("steps", []))
            return f"{pre.get('title', 'Pre-EVA Checklist')}: {steps}"

        # 2. Mission manifest
        if any(kw in t for kw in ["crew", "commander", "manifest", "habitat", "équipage", "commandant"]):
            manifest = self.kb_data.get("mission_manifest", {}).get("mission", {})
            if "commander" in t or "commandant" in t:
                return f"Mission Commander: {manifest.get('crew', {}).get('commander')}."
            if any(kw in t for kw in ["base", "habitat", "station"]):
                return f"Base Station: {manifest.get('base_station')} at {manifest.get('coordinates')}."
            crew = ", ".join(manifest.get("crew", {}).values())
            return f"Mission {manifest.get('code')} crew: {crew}."

        # 3. Smart Procedure Navigation (rules 1, 2, 3, 4)
        proc_reply = self._query_procedures_smart(t)
        if proc_reply:
            return proc_reply

        # 4. Geology codes
        if any(kw in t for kw in ["geology", "sample", "rock", "regolith", "basalt", "breccia",
                                    "géologie", "echantillon", "roche"]):
            geo = self.kb_data.get("geology_codes", {}).get("geology", {})
            if any(kw in t for kw in ["protocol", "how", "procedure", "comment"]):
                return f"Geology sampling protocol: {geo.get('sampling_protocol')}"
            codes = geo.get("codes", {})
            matched = [v for k, v in codes.items()
                       if k.lower() in t or any(alias in t for alias in [k.lower()[:3]])]
            if matched:
                return " ".join(matched)
            return f"Geology protocol: {geo.get('sampling_protocol')}. Codes: {', '.join(codes.keys())}."

        # 5. Suit manual
        if any(kw in t for kw in ["spec", "manual", "limit", "channel", "frequency", "battery",
                                    "pressure", "temperature", "canal", "fréquence", "limite"]):
            suit = self.kb_data.get("suit_manual", {}).get("suit", {})
            if any(kw in t for kw in ["channel", "radio", "frequency", "comm", "canal"]):
                comms = suit.get("communications", {})
                return f"Primary channel: {comms.get('primary_channel')}. Backup: {comms.get('backup_channel')}."
            if any(kw in t for kw in ["battery", "power", "batterie"]):
                bat = suit.get("battery", {})
                return f"Battery capacity: {bat.get('capacity_wh')} Wh, runtime: {bat.get('max_runtime_hours')} hours."
            if any(kw in t for kw in ["pressure", "pression"]):
                pres = suit.get("pressure", {})
                return f"Nominal pressure: {pres.get('nominal_hpa')} hPa (range: {pres.get('min_hpa')} – {pres.get('max_hpa')} hPa)."
            if any(kw in t for kw in ["temperature", "thermal"]):
                therm = suit.get("thermal", {})
                return f"Thermal range: {therm.get('min_temp_c')} to {therm.get('max_temp_c')} °C."

        return None

    def _detect_procedure_name(self, text: str) -> Optional[str]:
        for doc_name in self.procedure_navigators:
            name_words = [
                w for w in re.split(r'[_\s]+', doc_name.lower())
                if len(w) >= 7 and w not in STOP_WORDS and w != "procedure"
            ]
            if any(w in text.lower() for w in name_words):
                return doc_name
        return None

    def _format_step_response(self, nav: ProcedureNavigator, step: Dict) -> str:
        """Rule 4: Check if step is a decision point, otherwise format standard concise step."""
        if step.get("is_decision"):
            self._pending_decision = {"step": step, "doc": nav.doc_name}
            return (
                f"Step {step['number']} — {step['phase']}: {step['text']}. "
                f"Are additional measurements required? Say YES to return to laser targeting (Step 4), or NO to proceed to End of EVA (Step 11)."
            )
        return nav.format_step(step)

    def _query_procedures_smart(self, text: str) -> Optional[str]:
        t = text.lower()

        nav_proc = (self.procedure_navigators.get(self._current_procedure)
                    if self._current_procedure else None)

        # ── Repeat ─────────────────────────────────────────────────────────────
        if nav_proc and REPEAT_PATTERNS.search(text) and self._last_step:
            return self._format_step_response(nav_proc, self._last_step)

        # ── Previous Step ──────────────────────────────────────────────────────
        if nav_proc and PREV_STEP_PATTERNS.search(text) and self._last_step:
            prev = nav_proc.get_by_number(self._last_step["number"] - 1)
            if prev:
                self._last_step = prev
                return self._format_step_response(nav_proc, prev)
            return "Already at the first step."

        # ── Next Step ──────────────────────────────────────────────────────────
        bare_next = NEXT_STEP_PATTERNS.search(text)
        meaningful_kws = [w for w in re.findall(r"\b[a-z]{3,}\b", t) if w not in STOP_WORDS]
        if nav_proc and bare_next and not meaningful_kws and self._last_step:
            nxt = nav_proc.next_step_after(self._last_step)
            if nxt:
                self._last_step = nxt
                return self._format_step_response(nav_proc, nxt)
            return f"Step {self._last_step['number']} is the last step."

        keywords = meaningful_kws
        step_num_match = STEP_NUMBER_PATTERN.search(text)
        named_procedure = self._detect_procedure_name(text)

        if named_procedure and self._current_procedure != named_procedure:
            self._current_procedure = named_procedure
            self._last_step = None

        # ── RULE 1: Ambiguity Check for Step N ─────────────────────────────────
        if step_num_match:
            n = int(step_num_match.group(1))
            search_docs = [named_procedure] if (named_procedure and named_procedure in self.procedure_navigators) else list(self.procedure_navigators.keys())
            
            all_matches = []
            for doc_name in search_docs:
                nav = self.procedure_navigators[doc_name]
                for s in nav.get_all_by_number(n):
                    doc_title = doc_name.replace("_procedure", "").replace("_", " ").title()
                    all_matches.append((doc_title, s["phase"], nav, s))

            # Check if phase name was explicitly mentioned in user query
            user_mentioned_phase = any(
                any(pw in t for pw in [w for w in re.split(r'[_\s]+', phase.lower()) if len(w) >= 4 and w not in STOP_WORDS])
                for _, phase, _, _ in all_matches
            )

            if len(all_matches) > 1 and not user_mentioned_phase:
                self._pending_clarification = {"type": "step_n", "step_number": n, "matches": all_matches}
                doc_names_unique = list(dict.fromkeys([doc for doc, _, _, _ in all_matches]))
                if len(doc_names_unique) > 1:
                    options_str = " or ".join(doc_names_unique)
                    return f"Which procedure are you working with? {options_str}?"
                else:
                    phases_unique = list(dict.fromkeys([phase for _, phase, _, _ in all_matches]))
                    options_str = " or ".join(phases_unique)
                    return f"Step {n} exists in {options_str}. Which section of {doc_names_unique[0]} are you performing?"

        # ── RULE 2: Sub-section / Category Jumping ─────────────────────────────
        matched_phase_steps = []
        phase_stop_words = STOP_WORDS | {"procedure", "procedures", "step", "steps", "mode", "method", "sample", "samples", "rock", "data"}
        for doc_name, nav in self.procedure_navigators.items():
            if named_procedure and doc_name != named_procedure:
                continue
            for phase_name in nav.phases:
                phase_words = [w for w in re.split(r'[_\s]+', phase_name.lower()) if len(w) >= 4 and w not in phase_stop_words]
                if any(pw in t for pw in phase_words):
                    first_step = nav.get_first_step_of_phase(phase_name)
                    if first_step:
                        doc_title = doc_name.replace("_procedure", "").replace("_", " ").title()
                        matched_phase_steps.append((doc_title, nav, first_step))

        if matched_phase_steps:
            if len(matched_phase_steps) == 1 or named_procedure:
                doc_title, nav, step = matched_phase_steps[0]
                self._current_procedure = nav.doc_name
                self._last_step = step
                return self._format_step_response(nav, step)
            elif len(matched_phase_steps) > 1:
                self._pending_clarification = {"type": "phase", "matches": [(d, s["phase"], n, s) for d, n, s in matched_phase_steps]}
                doc_names_unique = list(dict.fromkeys([doc for doc, _, _ in matched_phase_steps]))
                options = " or ".join(doc_names_unique)
                return f"Which procedure are you working with? {options}?"

        # ── Standard Keyword / Direct Step Lookup ─────────────────────────────
        search_order = []
        if self._current_procedure and self._current_procedure in self.procedure_navigators:
            search_order.append(self._current_procedure)
        for doc_name in self.procedure_navigators:
            if doc_name not in search_order:
                search_order.append(doc_name)

        for doc_name in search_order:
            nav = self.procedure_navigators[doc_name]
            if not nav.steps:
                continue

            if step_num_match:
                n = int(step_num_match.group(1))
                step = nav.get_by_number(n)
                if step:
                    self._current_procedure = doc_name
                    self._last_step = step
                    return self._format_step_response(nav, step)

            if keywords:
                matched_step = nav.find_best_step(keywords)
                if matched_step:
                    self._current_procedure = doc_name
                    self._last_step = matched_step
                    return self._format_step_response(nav, matched_step)

        if step_num_match and not self._current_procedure:
            return "Which procedure? Say the procedure name first, for example: 'Caillou step 7'."

        return None

    def reset_session(self) -> None:
        """Reset active procedure session and return to standby state."""
        self._current_procedure = None
        self._last_step = None
        self._pending_decision = None
        self._pending_clarification = None
