#!/usr/bin/env python3
"""Russian text rules that need no model.

Everything here is decided from the string itself, so the same answer comes out every time
and nothing is spent on tokens. The rules are the mechanical half of the review: typography,
homoglyphs, letter-level typos, register, and the cheap half of coherence (a quotation inside a
narration, a reported verb inside a spoken line, a pronoun before anyone was introduced).

The subjective half -- does the line answer the question, does it follow the previous line,
is the emotion right -- is not here. That goes to the controller agent, and the split matters:
if a rule is wrong, the reader sees one false line and moves on; if a model is wrong, it invents
a defect and sends a good line back for rewriting.

Every rule returns `Finding` records with a stable `code`, a `level` and a short Russian `hint`,
because the report is read by a Russian reviewer and the code is what a filter is written
against.
"""

import re
import unicodedata

import ru_lexicon as lex

# Levels. ERROR breaks the text or breaks the engine, WARN is probably a defect, INFO is a
# style note the editor decides on.
ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"

CYR = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
LATIN = "abcdefghijklmnopqrstuvwxyz"
MASC_PRONOUNS = ("он", "его", "ему", "им", "нём", "него")
FEM_PRONOUNS = ("она", "её", "ее", "ей", "ею", "неё", "нее")
# `его` and `им` are left out of the gender check on purpose: they agree with an inanimate
# object as well («Ника разорвала его по краю» is about an envelope), and a checker that shouts
# there is a checker nobody reads.
MASC_GENDERED = ("он", "нём", "нему")
FEM_GENDERED = ("она", "неё", "нею", "ней")

_LATIN_RE = re.compile(r"[%s]+" % LATIN, re.IGNORECASE)
_CYR_RE = re.compile(r"[а-яёА-ЯЁ]+")
CYR_RE = _CYR_RE
# A Latin run glued to Cyrillic inside one token: the classic `Айнkрад` of a weak model.
_MIXED_RE = re.compile(r"[А-Яа-яЁё][A-Za-z]+|[A-Za-z]+[А-Яа-яЁё]")
_DUP_LETTER_RE = re.compile(r"([а-яёa-z])\1\1", re.IGNORECASE)
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_REPORTED_SPEECH = re.compile(
    r"\b(он|она|они|асуна|кирито|сugоу|сачи|юи|пох|кляйн|хатклиф|хечклиф|агил)"
    r"\s+(сказал|сказала|говорит|говорила|спросил|спросила|ответил|ответила|заметил|"
    r"заметила|продолжил|продолжила|шепнул|шепнула|крикнул|крикнула|вспомнил|вспомнила)\b")
_ATTRIBUTION = re.compile(
    r"\b(говорит|сказал|сказала|спросил|спросила|ответил|ответила|повторяет|повторял|"
    r"повторила|думает|думал|думала|шепчет|шепнул|шепнула|кричит|вспоминает|замечает|"
    r"кивает|качает|улыбается|смеётся|смеется)\b")
_ELISION = re.compile(r"\b([а-яё]+)-(то|за|нибудь)\b")
_QUOTED = re.compile(r"[«\"]([^»\"]{1,400})[»\"]")


class Finding(dict):
    """One defect: a stable code, a level, where it is, and what to do about it."""

    def __init__(self, code, level, where="", text="", hint="", line=0, field="", axis="",
                 aggregate=""):
        super().__init__(code=code, level=level, where=where, line=line, field=field,
                         text=text, hint=hint, axis=axis or (code.split(".", 1)[0]
                                                            if "." in code else "judge"),
                         aggregate=aggregate)

    @property
    def bad(self):
        return self["level"] in (ERROR, WARN)


def _covered_by_phrase(text):
    """Spans of the text that sit inside an allowed multi-word Latin phrase."""
    spans = []
    low = text.lower()
    for phrase in lex.ALLOWED_PHRASES:
        start = low.find(phrase)
        while start >= 0:
            spans.append((start, start + len(phrase)))
            start = low.find(phrase, start + 1)
    return spans


def sentences(text):
    """Split a line into sentences, keeping the original strings."""
    return [s for s in (x.strip() for x in _SENT_SPLIT.split(text or "")) if s]


def words(text):
    return _WORD_RE.findall(text or "")


def skeleton(text):
    """A sentence reduced to a comparison key: case, punctuation, gender and numbers gone."""
    key = (text or "").lower()
    key = key.replace("ё", "е").replace("—", " ").replace("--", " ")
    key = _QUOTED.sub(" Q ", key)
    key = re.sub(r"[^\w\s]", " ", key, flags=re.UNICODE)
    key = re.sub(r"\b(он|она|они|оно|его|ее|её|им|ими|им\w*)\b", "Pron", key)
    key = re.sub(r"\b\d+\b", "N", key)
    key = re.sub(r"\s+", " ", key).strip()
    return key


# ------------------------------------------------------------------ typography

def check_typography(text, where="", line=0):
    out = []
    add = lambda *a, **k: out.append(Finding(*a, where=where, line=line, **k))

    if text != text.strip():
        add("typo.pad_space", WARN, text=text[:160],
            hint="пробел в начале или конце строки")
    if "  " in text:
        add("typo.double_space", ERROR, text=text[:160], hint="двойной пробел")
    if "\n" in text or "\t" in text:
        add("typo.control_char", ERROR, text=text[:160], hint="перенос строки или табуляция внутри реплики")
    if "\u00a0" in text:
        add("typo.nbsp", ERROR, text=text[:160], hint="неразрывный пробел, замени на обычный")
    if "\u2026" not in text and "..." in text:
        add("typo.dots", WARN, text=text[:160], hint="три точки вместо многоточия «…»")
    if text.count("«") != text.count("»"):
        # The house mistake: «Реплика, — говорит она. The attribution goes outside the
        # quotation: «Реплика», — говорит она.
        add("typo.quote_unclosed", ERROR, text=text[:160],
            hint="кавычки «…» не сходятся: реплика с ремаркой пишется «Реплика», — говорит она")
    if '"' in text:
        numeric = re.search(r'"[\d\s.,:;!?-]+"', text) is not None
        add("typo.straight_quotes", INFO if numeric else ERROR, text=text[:160],
            hint="прямые кавычки вместо «ёлочек»")
    for sent in sentences(text):
        if re.search(r"([,;:])\1", sent):
            add("typo.repeat_punct", ERROR, text=sent[:160], hint="повтор знака препинания")
        if re.search(r"([!?])\1", sent):
            add("typo.exclaim", INFO, text=sent[:160], hint="«!!» или «??»: в книжной речи не ставят")
        if re.search(r"\s+[,.!?;:]", sent):
            add("typo.space_before_punct", ERROR, text=sent[:160], hint="пробел перед знаком препинания")
        if re.search(r"[а-яёa-z][,.!?](?=[А-ЯA-Z«])", sent):
            add("typo.no_space_after_punct", ERROR, text=sent[:160], hint="нет пробела после знака препинания")
    if "--" in text:
        add("typo.dash_pair", INFO, text=text[:160],
            hint="двойной дефис вместо тире «—»", aggregate="тире «--» вместо «—»")
    if re.search(r"(?<=[а-яёa-z]) - (?=[а-яёa-z])", text):
        add("typo.hyphen_dash", WARN, text=text[:160], hint="одиночный дефис вместо тире «—»")
    for sent in sentences(text):
        if sent.lstrip().startswith("—") and re.match(r"^—\s+[а-яё]", sent.lstrip()):
            add("typo.lowercase_after_dash", WARN, text=text[:160],
                hint="тире открывает фразу, а дальше маленькая буква: «%s»"
                     % sent.strip()[:60])
    return out


# ------------------------------------------------------------------ letter level

def check_letters(text, where="", line=0):
    out = []
    add = lambda *a, **k: out.append(Finding(*a, where=where, line=line, **k))

    for match in _MIXED_RE.finditer(text):
        add("typo.latin_in_cyrillic", ERROR, text=text[:160],
            hint="латиница внутри русского слова: %s" % match.group(0))
    covered = _covered_by_phrase(text)
    for match in _LATIN_RE.finditer(text):
        word = match.group(0)
        if any(a <= match.start() < b for a, b in covered):
            continue
        if not lex.is_latin_allowed(word):
            add("typo.english_word", WARN, text=text[:160],
                hint="английское слово «%s» в русском тексте" % word)
    triple = _DUP_LETTER_RE.search(text)
    if triple:
        add("typo.double_letter", ERROR, text=text[:160],
            hint="тройная буква «%s»" % triple.group(0))
    if re.search(r"\b[а-яё]+\d|\d[а-яё]+\b", text):
        add("typo.alnum", INFO, text=text[:160], hint="слово и цифра слитно, проверь границы")
    for word in words(text):
        for wrong, right in lex.YO_FORMS:
            if word.lower() == wrong and right != wrong:
                add("typo.yo_variant", WARN, text=text[:160],
                    hint="«%s» — правильно «%s», раз в тексте уже есть «ё»" % (word, right))
    return out


# ------------------------------------------------------------------ register

def check_register(text, kind="narration", where="", line=0):
    out = []
    add = lambda *a, **k: out.append(Finding(*a, where=where, line=line, **k))
    low = " " + text.lower() + " "

    def present(word):
        """Whole-word match, so «сп» does not fire inside «спасти»."""
        if " " in word.strip() or not word.strip():
            return word in low
        return re.search(r"(?<![а-яё])%s(?![а-яё])" % re.escape(word.strip()), low) is not None

    for word in lex.BAN_SLANG:
        if present(word):
            add("style.slang", ERROR, text=text[:160],
                hint="разговорное/интернет-сленг «%s», здесь нужен литературный русский" % word.strip())
    for word in lex.PLACEHOLDER:
        if present(word):
            add("style.placeholder", ERROR, text=text[:160],
                hint="заглушка или служебная пометка «%s» попала в текст" % word)
    for word in lex.CLICHE:
        if present(word):
            add("style.cliche", INFO, text=text[:160],
                hint="штамп «%s», проверь, не подходит ли деталь" % word)
    head = low.lstrip()
    for word in lex.BAD_OPENERS:
        if head.startswith(word.strip().rstrip(",")):
            add("style.opener", WARN, text=text[:160], hint="разговорное начало «%s»" % word.strip())
    if kind != "narration" and re.match(r"^\s*(он|она|они)\s+[а-яё]+\s+(стоит|сидит|смотрит|идёт|идет)", text):
        add("style.stage_in_dialogue", WARN, text=text[:160],
            hint="в реплике описание в третьем лице, это авторский текст")
    if "*" in text or re.search(r"(?<![A-Za-z0-9])_[A-Za-z]", text):
        add("style.markup", WARN, text=text[:160], hint="звёздочки или подчёркивания в реплике")
    if re.search(r"\(.*\)", text):
        add("style.brackets", WARN if kind != "narration" else INFO, text=text[:160],
            hint="скобки в реплике: TTS прочитает их, а игрок увидит лишнее")
    if "http" in low or "www." in low:
        add("style.url", WARN, text=text[:160], hint="ссылка в художественном тексте")
    if kind != "field":
        # A world field is a list of traits written without a capital, and that is how the
        # project writes them; a spoken or narrated line always starts with a capital.
        for sent in sentences(text):
            if sent.islower() and sent[:1].isalpha():
                add("typo.lowercase_start", WARN, text=text[:160],
                    hint="предложение с маленькой буквы: «%s»" % sent.strip()[:60])
    return out


# ------------------------------------------------------------------ form

def check_form(text, kind="narration", where="", line=0):
    """The house rule for a line of dialogue: speech in the quotes, the tag on its own line.

    `«О», -- говорит она, и поднимает голову.` mixes what the character says with what the
    author does, and the game cannot show that: the engine plays one step as one line, either
    the character or the narrator. So this is a form error, not a taste question.
    """
    out = []
    add = lambda *a, **k: out.append(Finding(*a, where=where, line=line, **k))
    if "«" not in text:
        return out
    outside = _QUOTED.sub(" ", text)
    tag = _ATTRIBUTION.search(outside)
    if tag:
        add("form.quote_with_tag", WARN, text=text[:160],
            hint="в одной строке и реплика, и ремарка (%s). Реплику оставить одну, действие "
                 "вынести отдельной строкой" % tag.group(0))
    tail = re.search(r"«[^»]{2,}»\s*,?\s*(?:—|--)\s*([^,.!?]{0,40})", text)
    if tail and _ATTRIBUTION.search(tail.group(1)):
        add("form.tag_after_quote", WARN, text=text[:160],
            hint="ремарка стоит сразу после закрытой кавычки: «Реплика», — говорит она; "
                 "в этом мире реплика идёт отдельной строкой, а действие — своей")
    if re.search(r"(^|[.!?]\s*)—\s*«", text):
        add("form.dash_then_quote", INFO, text=text[:160],
            hint="тире перед прямой речью: «Реплика». — говорит она")
    return out


# ------------------------------------------------------------------ length

def check_length(text, kind="narration", where="", line=0):
    out = []
    n = len((text or "").strip())
    if n < lex.TEXT_MIN:
        # A one-word answer is good dialogue, a one-word paragraph of narration is not.
        out.append(Finding("struct.short_text", WARN if kind == "narration" else INFO,
                           where=where, line=line, text=text[:160],
                           hint="строка короче %d символов: «%s»" % (lex.TEXT_MIN, text.strip())))
    limit = lex.FIELD_MAX if kind == "field" else lex.TEXT_MAX
    if n > limit:
        out.append(Finding("struct.long_text", WARN if kind != "field" else INFO,
                           where=where, line=line, text=text[:160],
                           hint="%d символов, движок обрежет до %d" % (n, limit)))
    if kind == "narration" and n > lex.NARRATION_MAX:
        out.append(Finding("style.wall", INFO, where=where, line=line, text=text[:160],
                           hint="кусок повествования длиннее %d символов, разбей на две строки" % lex.NARRATION_MAX))
    if kind == "narration" and len(sentences(text)) > 4:
        out.append(Finding("style.sentence_run", INFO, where=where, line=line, text=text[:160],
                           hint="%d предложений подряд, прочитается как стена" % len(sentences(text))))
    return out


# ------------------------------------------------------------------ coherence proxies

def check_coherence(text, kind="narration", where="", line=0, mentions=(), introduced=()):
    """Cheap structural coherence: attribution, point of view, pronouns."""
    out = []
    add = lambda *a, **k: out.append(Finding(*a, where=where, line=line, **k))
    low = text.lower()
    sent_list = sentences(text)
    # Name and pronoun disagree inside one sentence. Only names with a known gender count, so
    # a place name can never produce a finding.
    known_names = [n for n in list(mentions) + proper_nouns(text)
                   if n.lower() in lex.GENDER_FEMALE or n.lower() in lex.GENDER_MALE]

    if kind == "narration":
        # `«Реплика», — говорит она` is a deliberate construction: the author's line carries the
        # speech with a tag. Speech with no tag is a defect, because the engine shows the
        # quotation marks as narration and nobody speaks.
        tagged = bool(_ATTRIBUTION.search(text))
        if not tagged:
            for match in _QUOTED.finditer(text):
                if _written_object(text):
                    break  # the quote is what the note or the letter says
                if text.count("«") == text.count("»") and _is_speech(match.group(1)):
                    # Two readings are possible and a script cannot choose: a character's line
                    # that lost its speaker, or a written note that the author quotes on purpose.
                    add("coh.quote_in_narration", INFO, text=text[:160],
                        hint="речь в авторском тексте: «%s». Если это реплика — нужен "
                             "speaker, иначе её прочитает рассказчик; если это текст записки "
                             "или письма — всё верно" % match.group(1)[:50])
        if re.match(r"^\s*(я|мне|меня|мой|моя|мои|мы|нас|нам|сво[её])\b", low):
            add("coh.first_person_narration", ERROR, text=text[:160],
                hint="повествование от первого лица: «%s»" % text.strip()[:40])
    if kind == "dialogue":
        match = _REPORTED_SPEECH.search(text)
        if match:
            add("coh.reported_in_dialogue", ERROR, text=text[:160],
                hint="в реплике чужой голос: «%s», это должен быть авторский текст"
                     % match.group(0))
        if not text.strip().startswith(("«", "— ", "-- ")) and _QUOTED.search(text):
            add("coh.quote_style", INFO, text=text[:160],
                hint="в этом мире прямая речь пишется в «ёлочках»")

    # A pronoun with nobody named yet anywhere in the story. Deliberately narrow: once any
    # name has been mentioned the reader has an antecedent, and guessing further is noise.
    if not introduced:
        for sent in sent_list:
            sl = sent.lower()
            if pron_used(sl, FEM_PRONOUNS) or pron_used(sl, MASC_PRONOUNS):
                add("coh.pronoun_first", INFO, text=text[:160],
                    hint="история начинается с «%s», а никто ещё не назван: игрок не понимает, "
                         "о ком речь" % first_pronoun(sl))
                break

    for sent in sent_list:
        sl = sent.lower()
        for name in known_names:
            if name not in sl or len(name) < 4:
                continue
            if name in lex.GENDER_FEMALE and _subject_pronoun(sent, MASC_GENDERED):
                add("coh.gender_mismatch", WARN, text=sent[:160],
                    hint="«%s» и «он» как подлежащее в одном предложении" % name)
            if name in lex.GENDER_MALE and _subject_pronoun(sent, FEM_GENDERED):
                add("coh.gender_mismatch", WARN, text=sent[:160],
                    hint="«%s» и «она» как подлежащее в одном предложении" % name)

    if re.search(r"\bне\b[\w\s]{0,24}\bне\b", low):
        add("coh.double_negative", WARN, text=text[:160],
            hint="два отрицания рядом, проверь смысл: «%s»"
                 % re.search(r"\bне\b[\w\s]{0,24}\bне\b", low).group(0)[:40])
    if re.search(r"\b(и|а|но|или)\s*,\s*[а-яё]", low):
        add("coh.comma_join", INFO, text=text[:160], hint="союз через запятую")
    return out


PROPER_RE = re.compile(r"(?<![.!?…«]\s)(?<!^)([А-ЯЁ][а-яё]{2,})")


def proper_nouns(text):
    """Capitalised Cyrillic words that are not sentence-initial: names, places, titles."""
    out = []
    for sentence in sentences(text):
        for match in PROPER_RE.finditer(sentence):
            out.append(match.group(1))
    return out


_WRITTEN_OBJECT = re.compile(
    r"(записк|письм|конверт|слов|надпис|фраз|инструкц|текст|обороте|страниц|строк|столб|"
    r"доске|вывеск|газет)", re.IGNORECASE)


def _written_object(text):
    """True when the narration names a physical text, so the quotation is what it says."""
    return bool(_WRITTEN_OBJECT.search(text[:120]))


def _is_speech(quoted):
    """Distinguish a spoken line from a title: «Рыцари Крови» is a name, «Он придёт» is speech."""
    body = quoted.strip()
    if not body:
        return False
    if re.search(r"\b(я|ты|он|она|мы|вы|они|мне|тебе|нам|вам)\b", body.lower()):
        return True
    if body[-1] in "?!…":
        return True
    tokens = [t for t in re.findall(r"\w+", body)]
    if len(tokens) >= 5 and not all(t[:1].isupper() for t in tokens):
        return True
    return False


_PREPOSITION = ("на", "у", "к", "с", "о", "об", "от", "при", "для", "за", "по", "из", "про",
               "перед", "над", "под", "в", "во", "до", "около", "рядом")


def _subject_pronoun(sentence, pronouns):
    """A pronoun in subject position. «Вера посмотрела на него» is correct Russian, so the word
    before the pronoun decides: a preposition means it is an object referring to someone else."""
    low = sentence.lower()
    for pronoun in pronouns:
        for match in re.finditer(r"\b%s\b" % pronoun, low):
            before = re.findall(r"[а-яё]+", low[:match.start()])
            if before and before[-1] in _PREPOSITION:
                continue
            return True
    return False


def pron_used(low_sentence, pronouns):
    return any(re.search(r"\b%s\b" % p, low_sentence) for p in pronouns)


def first_pronoun(low_sentence):
    for sent_p in MASC_PRONOUNS + FEM_PRONOUNS:
        if re.search(r"\b%s\b" % sent_p, low_sentence):
            return sent_p
    return "он/она"


# ------------------------------------------------------------------ everything at once

def check_text(text, kind="narration", where="", line=0, mentions=(), introduced=()):
    """All per-line rules for one line of the story."""
    text = (text or "").strip()
    if not text:
        return [Finding("struct.empty_text", ERROR, where=where, line=line,
                        hint="пустая строка в сюжете")]
    findings = []
    findings += check_typography(text, where, line)
    findings += check_letters(text, where, line)
    findings += check_register(text, kind, where, line)
    findings += check_form(text, kind, where, line)
    findings += check_length(text, kind, where, line)
    findings += check_coherence(text, kind, where, line, mentions, introduced)
    return findings


def visible(text):
    """The text as a terminal prints it, with the invisible characters made visible."""
    out = []
    for ch in text or "":
        if ch in ("\u00a0", "\u202f"):
            out.append("<nbsp>")
        elif ch == "\t":
            out.append("<tab>")
        elif ch == "\n":
            out.append("<br>")
        elif unicodedata.category(ch) in ("Cc", "Cf") and ch not in "\r":
            out.append("<%04x>" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)
