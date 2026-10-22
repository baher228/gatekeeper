from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path

SEED_KIND_COUNTS = {
    "strong_builder": 30,
    "weak_vague": 24,
    "first_timer_concrete": 18,
    "researcher_paper": 12,
    "new_account_polished": 12,
    "recruiter_seller": 12,
    "scammer": 12,
}
EVAL_KIND_COUNTS = {
    "strong_builder": 39,
    "weak_vague": 30,
    "first_timer_concrete": 23,
    "researcher_paper": 15,
    "new_account_polished": 15,
    "recruiter_seller": 14,
    "scammer": 14,
}

FIRST_NAMES = (
    "Ada", "Aisha", "Alex", "Amara", "Ben", "Chloe", "Dara", "Elliot",
    "Ellis", "Fatima", "Grace", "Harriet", "Idris", "Imogen", "Jamal",
    "Jamie", "Jonah", "Leah", "Leo", "Lina", "Maya", "Mina", "Nadia",
    "Noah", "Omar", "Priya", "Ravi", "Rosa", "Sam", "Sana", "Theo",
    "Toby", "Uma", "Victor", "Will", "Yasmin", "Yuki", "Zara", "Zoe",
)
LAST_NAMES = (
    "Adams", "Ahmed", "Ali", "Baker", "Bennett", "Brown", "Campbell",
    "Carter", "Clarke", "Davies", "Edwards", "Evans", "Foster", "Green",
    "Hall", "Hughes", "Khan", "Lewis", "Morgan", "Murphy", "Patel",
    "Reed", "Shah", "Singh", "Taylor", "Thomas", "Walker", "Ward",
    "White", "Wright", "Young", "Basu", "Chen", "Ellis", "Flores",
    "Grant", "James", "Kaur", "Martin", "Okafor",
)

PHRASE_POOLS = {
    "strong_builder": [
        ["I shipped a working AI demo for local community gardens.", "I built and launched a small AI product for London residents.", "I shipped a useful prototype that people can try today."],
        ["The public repo has tests, setup instructions, and a short roadmap.", "The repository includes a live demo and clear implementation notes.", "I keep the code public and document what I have learned."],
        ["I have been testing it with real users and fixing the rough edges.", "I run a few user sessions each month and iterate from their feedback.", "The project is in active use and I have a list of measurable improvements."],
        ["I am based in London and build with local groups.", "I regularly work with London makers and community organizations.", "I am in London and enjoy sharing practical engineering lessons."],
        ["I will give a short demo and help others test their projects.", "I can offer code reviews and thoughtful feedback to other builders.", "I want to share progress and help the group ship useful things."],
        ["The project uses language models for a narrow, well-tested workflow.", "I use AI where it improves the product and measure whether it helps.", "I am exploring practical LLM evaluation rather than adding AI for its own sake."],
    ],
    "weak_vague": [
        ["I would like to meet people who are interested in technology.", "I am hoping to do some networking with local builders.", "I want to learn more about what everyone is working on."],
        ["I have not settled on a project idea yet.", "I am still looking for an idea and have not started building.", "I am curious about startups but do not have a demo to share."],
        ["I would like to hear about AI and maybe try it sometime.", "I am interested in learning about new tools from the group.", "I am hoping to get inspiration and see what other people make."],
        ["I am around London and would enjoy meeting more people.", "I live near London and am looking for a friendly community.", "I am interested in attending meetups and making connections."],
        ["I do not have a repo or a prototype to show yet.", "I have not written a project plan or tested anything with users.", "For now I can mostly listen and learn from the group."],
        ["I might share an idea later if I find something interesting.", "I am open to exploring different directions with other people.", "I do not know what I could contribute at the moment."],
    ],
    "first_timer_concrete": [
        ["I am building a simple bus-stop accessibility map for people using wheelchairs.", "My first project is a quiet-space finder for neurodivergent students.", "I am making a small tool that maps free community fridges."],
        ["The first version lets people add a place and verify its opening hours.", "I have sketched the user flow and built a clickable first screen.", "I have a short list of local users who will try the prototype."],
        ["I am new to coding, so the project is small and focused.", "This is my first build, and I am learning by shipping one feature at a time.", "I started with a weekend prototype and am improving it each week."],
        ["I am based in London and want to test it with a nearby community group.", "I can ask local volunteers to try the tool and report what is confusing.", "I would like feedback from people who know the London area."],
        ["I will show the prototype and give other first-timers useful feedback.", "I can share what I learn and help test other people's demos.", "I will bring a clear demo and ask for specific feedback."],
        ["I want to make public information easier to find.", "The goal is a practical tool that helps people plan a local trip.", "I am keeping the first release free and simple to use."],
    ],
    "researcher_paper": [
        ["I wrote a short paper comparing language-model evaluation methods.", "My project evaluates how well small language models explain public-service forms.", "I am studying reproducible evaluation for AI tools used by researchers."],
        ["I have a Devpost project with the experiments and a small demo.", "The project page links to an evaluation dashboard and a write-up.", "I documented the work in a project page and shared an early result."],
        ["The repository is small because most of the work is experiments and analysis.", "I have only a few repos, but this work includes data and repeatable tests.", "I focus on careful evaluation rather than building a large product."],
        ["I am interested in AI and language-model reliability.", "The work compares model behavior on practical London service questions.", "I am looking for peers who care about transparent AI evaluation."],
        ["I can present the paper and invite critique of the methodology.", "I will share the experiment and help others improve their evaluation plans.", "I am happy to give feedback on demos and research write-ups."],
        ["I am based in London and collaborate with local research groups.", "I regularly work with London researchers and independent builders.", "I would like to connect with people building useful AI systems."],
    ],
    "new_account_polished": [
        ["I am building a polished AI assistant for independent bookshops.", "I designed a focused workflow tool for local nonprofit teams.", "I am developing a practical service that helps small London organizations."],
        ["The product brief, user interviews, and roadmap are written up.", "I have a clear user journey and a plan for measurable testing.", "I have scoped a small release and documented the product decisions."],
        ["I would love to demo the concept and get detailed product feedback.", "I can share the research and help other builders think through onboarding.", "I will bring a short presentation and useful questions for the group."],
        ["I am based in London and have spoken with potential users.", "I have done discovery interviews with a few local organizations.", "The first release is aimed at people working in the London area."],
        ["I want to use language models only where they improve the experience.", "AI is part of the design, but user trust and evaluation come first.", "I am exploring LLM tools with a careful focus on reliability."],
        ["The project is at an early stage while I validate the workflow.", "I have not published a repository yet, but the first build is underway.", "I am turning a detailed prototype plan into a first implementation."],
    ],
    "recruiter_seller": [
        ["Our agency is recruiting founders for a paid growth package.", "I am hiring sales representatives for a crypto promotion campaign.", "We are looking for ambitious people to join our marketing network."],
        ["DM me for guaranteed leads and a special launch discount.", "Message me today to buy a sponsored placement in our newsletter.", "Contact me for a limited offer with guaranteed returns."],
        ["I want to pitch our consulting service to the whole community.", "We can sell you a verified audience and a fast route to users.", "I am here to recruit clients for our paid growth program."],
        ["The package includes premium access and guaranteed profit.", "We offer guaranteed results if you sign up before the offer expires.", "Our team can promote your token and bring in new investors."],
        ["I am not bringing a project demo or asking for product feedback.", "I would like to use the meetup to find customers.", "The main goal is to recruit people for our service."],
        ["I will send everyone the details after they DM me.", "Join our channel to see the latest deals and referral rewards.", "I can share a link for anyone interested in investing."],
    ],
    "scammer": [
        ["Claim your bonus now and reply to receive the exclusive reward.", "Limited-time offer: contact me today to claim your prize.", "You have been selected; call now before this offer expires."],
        ["Guaranteed cash returns for anyone who acts immediately.", "Send a message now to unlock your special reward.", "Reply with your details and I will arrange the payment."],
        ["This offer is urgent and available only for a short time.", "I can share a private link with everyone who is interested.", "Do not miss this chance to claim a free prize."],
        ["I am promoting a referral offer to the whole group.", "DM me for the link and details about the reward.", "Invite your friends to join before the promotion ends."],
        ["The investment has guaranteed returns with no risk.", "This deal includes a bonus for anyone who signs up today.", "I can send the payment instructions after you contact me."],
        ["I want to share an exclusive promotion with London builders.", "The offer is simple: message me to get started.", "There is no need to wait; claim your reward now."],
    ],
}

PROJECT_NAMES = (
    "Civic Lens", "Quiet Hours", "Garden Notes", "Access Map", "Open Routes",
    "Local Signals", "Model Bench", "Paper Trail", "Common Ground",
)
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "sms_spam_sample.json"


@lru_cache(maxsize=1)
def _spam_rows() -> tuple[str, ...]:
    try:
        data = json.loads(DATA_PATH.read_text())
    except (OSError, ValueError):
        return ()
    return tuple(
        row.get("text", row.get("sms", ""))
        for row in data.get("rows", [])
        if row.get("label") in ("spam", 1, "1") and row.get("text", row.get("sms"))
    )


def _text(rng: random.Random, kind: str) -> str:
    count = rng.randint(3, 6)
    pools = rng.sample(PHRASE_POOLS[kind], count)
    phrases = [rng.choice(pool) for pool in pools]
    if kind == "scammer":
        phrases[0] = rng.choice(_spam_rows() or (
            "URGENT! Claim your free prize now and contact me today.",
            "You have won a bonus reward; call now to claim it.",
        ))
    return " ".join(phrases)


def _category(rng: random.Random, kind: str) -> str:
    if kind == "first_timer_concrete":
        return "first_timer"
    if kind == "researcher_paper":
        return "researcher"
    if kind == "strong_builder":
        return rng.choices(("builder", "mentor", "vip"), weights=(0.72, 0.18, 0.10), k=1)[0]
    if kind == "weak_vague":
        return rng.choices(("builder", "mentor", "first_timer", "researcher"), weights=(0.7, 0.1, 0.1, 0.1), k=1)[0]
    if kind == "recruiter_seller":
        return rng.choices(("builder", "mentor"), weights=(0.8, 0.2), k=1)[0]
    return "builder"


def _github_profile(rng: random.Random, kind: str) -> tuple[bool, int | None, int, int, int | None]:
    if kind == "strong_builder":
        return True, rng.randint(400, 4200), rng.randint(5, 40), rng.randint(5, 700), rng.randint(0, 90)
    if kind == "weak_vague":
        has_profile = rng.random() < 0.45
        if not has_profile:
            return False, None, 0, 0, None
        return True, rng.randint(20, 1200), rng.randint(0, 2), rng.randint(0, 18), rng.choice((None, rng.randint(91, 360)))
    if kind == "first_timer_concrete":
        has_profile = rng.random() < 0.65
        if not has_profile:
            return False, None, 0, 0, None
        return True, rng.randint(1, 180), rng.randint(0, 1), rng.randint(0, 8), rng.choice((None, rng.randint(0, 90)))
    if kind == "researcher_paper":
        has_profile = rng.random() < 0.7
        if not has_profile:
            return False, None, 0, 0, None
        return True, rng.randint(100, 3000), rng.randint(0, 5), rng.randint(0, 80), rng.choice((None, rng.randint(0, 180)))
    if kind == "new_account_polished":
        return True, rng.randint(1, 29), rng.randint(0, 1), rng.randint(0, 8), rng.randint(0, 29)
    if kind == "recruiter_seller":
        has_profile = rng.random() < 0.6
        if not has_profile:
            return False, None, 0, 0, None
        return True, rng.randint(30, 3000), rng.randint(0, 6), rng.randint(0, 90), rng.choice((None, rng.randint(0, 365)))
    has_profile = rng.random() < 0.4
    if not has_profile:
        return False, None, 0, 0, None
    return True, rng.randint(1, 500), rng.randint(0, 1), rng.randint(0, 12), rng.choice((None, rng.randint(0, 120)))


def make_applicant(rng: random.Random, kind: str) -> dict:
    if kind not in PHRASE_POOLS:
        raise ValueError(f"Unknown synthetic applicant kind: {kind}")
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    token = f"{rng.getrandbits(24):06x}"
    handle = f"{first.lower()}{last.lower()}{token}"
    category = _category(rng, kind)
    has_github, account_age, repos, followers, recent_push = _github_profile(rng, kind)
    github = handle if has_github else None
    has_devpost = kind == "researcher_paper" or (
        kind == "strong_builder" and rng.random() < 0.65
    ) or (
        kind == "first_timer_concrete" and rng.random() < 0.2
    )
    projects = (
        rng.randint(1, 3) if kind == "researcher_paper"
        else rng.randint(1, 4) if has_devpost
        else 0
    )
    wins = rng.randint(0, min(2, projects)) if projects else 0
    project_name = rng.choice(PROJECT_NAMES)
    devpost = f"{handle}-project" if has_devpost else None
    sample = [
        {"name": project_name, "url": f"https://devpost.com/software/{handle}-project"}
    ] if projects else []
    email = f"{first.lower()}.{last.lower()}.{token}@example.com"
    applicant = {
        "name": f"{first} {last}",
        "email": email,
        "phone": f"+44 7700 900{rng.randrange(1000):03d}",
        "github": github,
        "devpost": devpost,
        "chat_handle": f"@{handle}",
        "what_build": _text(rng, kind),
        "category": category,
        "kind": kind,
    }
    applicant["evidence"] = {
        "github": {
            "status": "simulated",
            "login": github,
            "account_age_days": account_age,
            "public_repos": repos,
            "followers": followers,
            "recent_push_days": recent_push,
        },
        "devpost": {
            "status": "simulated",
            "projects": projects,
            "wins": wins,
            "sample": sample,
        },
        "stopforumspam": {
            "status": "simulated",
            "email_appears": False,
            "username_appears": False,
            "confidence": 0,
        },
    }
    return applicant


def lead_label(applicant: dict, rng: random.Random) -> str:
    """Synthetic lead policy; documented in README. Used to label seed history and the held-out eval set."""
    kind = applicant["kind"]
    accept = kind in ("first_timer_concrete", "researcher_paper", "strong_builder")
    if kind in ("scammer", "recruiter_seller", "new_account_polished", "weak_vague"):
        accept = False
    else:
        assert kind in ("first_timer_concrete", "researcher_paper", "strong_builder")
    if rng.random() < 0.08:
        accept = not accept
    return "accept" if accept else "decline"
