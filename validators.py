"""Validation rules for MDCE FleetHub (ported from the PHP validators.php).
Every validate_* function returns a LIST of error messages. Empty list = OK."""
import re
from datetime import date

NON_EMAIL_DOMAINS = [
    "youtube.com", "youtu.be", "facebook.com", "fb.com", "messenger.com",
    "instagram.com", "tiktok.com", "twitter.com", "x.com", "netflix.com",
    "spotify.com", "discord.com", "reddit.com", "whatsapp.com", "telegram.org",
    "snapchat.com", "pinterest.com", "linkedin.com", "twitch.tv", "roblox.com",
    "shopee.ph", "lazada.com.ph", "amazon.com", "wikipedia.org", "github.com",
    "google.com", "canva.com", "zoom.us", "tumblr.com", "quora.com",
]

KNOWN_EMAIL_PROVIDERS = [
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.com.ph", "yahoo.co.uk", "ymail.com", "rocketmail.com",
    "outlook.com", "outlook.ph", "hotmail.com", "hotmail.co.uk", "live.com", "msn.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "proton.me", "protonmail.com", "pm.me",
    "zoho.com", "gmx.com", "gmx.net", "mail.com", "yandex.com",
    "tutanota.com", "tuta.com", "fastmail.com", "hey.com",
]

POSITIONS = ["President", "Vice President", "Secretary", "Treasurer", "Auditor", "Manager", "Staff"]
LAGUNA_LGUS = [
    "Alaminos", "Bay", "Biñan City", "Cabuyao City", "Calamba City", "Calauan", "Cavinti",
    "Famy", "Kalayaan", "Liliw", "Los Baños", "Luisiana", "Lumban", "Mabitac", "Magdalena",
    "Majayjay", "Nagcarlan", "Paete", "Pagsanjan", "Pakil", "Pangil", "Pila", "Rizal",
    "San Pablo City", "San Pedro City", "Santa Cruz", "Santa Maria", "Santa Rosa City",
    "Siniloan", "Victoria",
]
REGIONS = ["Region IV-A (CALABARZON)"]

NAME_RE = re.compile(r"^(?:[^\W\d_]|[. ])+$")


def clean_name(s):
    """Removes extra spaces and makes every word start with a capital letter."""
    s = " ".join((s or "").split())
    return " ".join(w[:1].upper() + w[1:] for w in s.split(" "))


def validate_name(name):
    if name == "":
        return ["Name cannot be empty."]
    if len(name) < 3:
        return ["Name must contain at least 3 characters."]
    if len(name) > 50:
        return ["Name must not exceed 50 characters."]
    if not NAME_RE.match(name):
        return ["Name must contain letters, spaces and a period (.) only - no numbers or symbols."]
    if not re.search(r"[^\W\d_]", name):
        return ["Name must contain at least one letter."]
    return []


def validate_contact(c):
    if c == "":
        return ["Contact number cannot be empty."]
    if not re.fullmatch(r"[0-9]+", c):
        return ["Contact contains only numbers."]
    if len(c) != 11:
        return ["Contact number must contain exactly 11 digits."]
    if not c.startswith("09"):
        return ["Contact number must start with 09."]
    if re.fullmatch(r"09([0-9])\1{8}", c):
        return ["Contact number must not contain repeated identical numbers."]
    if re.fullmatch(r"(09){5}0", c):
        return ["Contact number must not contain repeated number patterns."]
    return []


def validate_password(p):
    if p == "":
        return ["Password cannot be empty."]
    if p.strip() == "":
        return ["Password cannot contain only spaces."]
    if re.search(r"\s", p):
        return ["Password must not contain spaces."]
    if len(p) < 6:
        return ["Password must contain at least 6 characters."]
    if len(p) > 20:
        return ["Password must not exceed 20 characters."]
    return []


def is_school_gov_email_domain(host):
    return bool(re.search(r"\.(edu|gov)(\.[a-z]{2})?$|\.ac\.[a-z]{2}$", host))


def domain_format_error(host, name, single_msg):
    if host == "" or not re.fullmatch(r"[a-z0-9.\-]+", host):
        return f"{name} contains invalid characters."
    if ".." in host:
        return f"{name} must not have consecutive dots (..)."
    if host.startswith(".") or host.endswith("."):
        return f"{name} must not start or end with a dot."
    labels = host.split(".")
    if "edu" in labels and "gov" in labels:
        return f"{name} cannot have both edu and gov."
    if len(labels) < 2:
        return f"{name} must have an extension like .com, .org or .ph."
    for label in labels:
        if len(label) < 2:
            return single_msg
        if label.startswith("-") or label.endswith("-"):
            return f"{name} must not start or end a part with a hyphen."
    if not re.fullmatch(r"[a-z]{2,}", labels[-1]):
        return f"{name} must end with a valid extension like .com, .org or .ph."
    return ""


def validate_email(email):
    if email == "":
        return ["Email cannot be empty."]
    if len(email) > 50:
        return ["Email must not exceed 50 characters."]
    if re.search(r"\s", email):
        return ["Email must not contain spaces."]
    if email.count("@") != 1:
        return ["Email must contain exactly one @ symbol."]

    local, domain = email.split("@")
    domain = domain.lower()
    errors = []

    if local == "":
        errors.append("Email username cannot be empty (nothing before @).")
    elif len(local) < 2:
        errors.append("Email username must contain at least 2 characters (single letters like c@gmail.com are not allowed).")
    elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._%+\-]*", local):
        errors.append("Email username may only contain letters, numbers and . _ % + - (and must start with a letter or number).")
    elif ".." in local or local.endswith("."):
        errors.append("Email username must not have consecutive dots or end with a dot.")

    if domain == "":
        errors.append("Email domain cannot be empty (nothing after @).")
        return errors

    err = domain_format_error(domain, "Email domain",
                              "Email domain must not have single-letter parts (like c@g.com).")
    if err:
        errors.append(err)
        return errors

    for blocked in NON_EMAIL_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            errors.append(f"{blocked} is a website, not an email provider. Use a real email like gmail.com or outlook.com.")
            return errors

    if domain in KNOWN_EMAIL_PROVIDERS or is_school_gov_email_domain(domain):
        return errors

    errors.append(f'"{domain}" is not a recognized email provider. Use a real email like gmail.com, outlook.com or yahoo.com, or a school/government email (.edu, .gov).')
    return errors


FIELD_CHECKS = {"name": validate_name, "email": validate_email, "contact": validate_contact}


# ---------- position and address (dropdowns) ----------
def get_position(f):
    p = f.get("position", "")
    if p == "Other":
        p = " ".join(f.get("position_other", "").split())
        if not re.fullmatch(r"[A-Za-zÀ-ÿ ]{2,50}", p):
            return None, "Please type your position (letters only, up to 50 characters)."
        return p, None
    if p not in POSITIONS:
        return None, "Please choose your position."
    return p, None


def get_address(f):
    muni = f.get("municipality", "")
    if muni not in LAGUNA_LGUS:
        return None, "Please choose your municipality / city."
    return muni + ", Laguna", None


def validate_person(f):
    """Checks name, contact, position and address. Returns (clean values, list of errors)."""
    errors = []
    name = clean_name(f.get("full_name"))
    contact = (f.get("contact_no") or "").strip()
    errors += validate_name(name)
    errors += validate_contact(contact)
    position, err = get_position(f)
    if err:
        errors.append(err)
    address, err = get_address(f)
    if err:
        errors.append(err)
    return {"full_name": name, "contact_no": contact, "position": position, "address": address}, errors


def form_vals(f):
    return {"muni": f.get("municipality", ""), "muni_other": f.get("municipality_other", ""),
            "region": f.get("region", ""), "position": f.get("position", ""),
            "position_other": f.get("position_other", "")}


def vals_from_admin(a):
    addr = a["address"] or ""
    muni = ""
    for suffix in (", Laguna", ", Region IV-A (CALABARZON)"):
        if addr.endswith(suffix):
            muni = addr[: -len(suffix)]
            break
    pos = a["position"] or ""
    return {
        "muni": muni if muni in LAGUNA_LGUS else "",
        "muni_other": "",
        "region": "",
        "position": pos if pos in POSITIONS else ("Other" if pos else ""),
        "position_other": pos if pos and pos not in POSITIONS else "",
    }

def validate_jeep(jeep_no, plate_no, route, registration_expiry):
    errors = []

    if jeep_no == "":
        errors.append("Jeep number cannot be empty.")
    elif len(jeep_no) > 10:
        errors.append("Jeep number must not exceed 10 characters.")
    elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]*", jeep_no):
        errors.append("Jeep number may contain letters, numbers, spaces and hyphens only.")

    if plate_no == "":
        errors.append("Plate number cannot be empty.")
    elif len(plate_no) > 20:
        errors.append("Plate number must not exceed 20 characters.")
    elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]*", plate_no):
        errors.append("Plate number may contain letters, numbers, spaces and hyphens only.")

    if len(route) > 100:
        errors.append("Route must not exceed 100 characters.")
    elif route and not re.fullmatch(r"[\w\s.,()/&-]+", route, flags=re.UNICODE):
        errors.append("Route contains characters that are not allowed.")

    if registration_expiry:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", registration_expiry):
            errors.append("Registration expiry must be a valid date.")
        else:
            try:
                date.fromisoformat(registration_expiry)
            except ValueError:
                errors.append("Registration expiry must be a real calendar date.")

    return errors