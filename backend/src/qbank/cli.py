import argparse
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.auth import hasher
from qbank.config import get_settings
from qbank.db import get_engine
from qbank.llm import OpenRouterClient, image_part
from qbank.llm.pricing import refresh_prices
from qbank.models import Chapter, Language, Lesson, Organization, Role, Subject, User
from qbank.services.llm_costs import org_month_spend, spend_by, total_spend


def create_admin(db: Session, org_name: str, email: str, password: str, name: str) -> None:
    org = db.scalar(select(Organization).where(Organization.name == org_name))
    if org is None:
        org = Organization(name=org_name)
        db.add(org)
        db.flush()
    db.add(
        User(
            org_id=org.id,
            email=email,
            name=name,
            role=Role.admin,
            password_hash=hasher.hash(password),
        )
    )
    db.commit()


def seed_dev(db: Session) -> None:
    if get_settings().env == "prod":
        raise ValueError("seed-dev is not available in production")
    name = "Demo School / مدرسة تجريبية"
    org = db.scalar(select(Organization).where(Organization.name == name))
    if org is None:
        org = Organization(name=name)
        db.add(org)
        db.flush()
    for role in Role:
        email = f"{role.value}@demo.local"
        if db.scalar(select(User).where(User.email == email)) is None:
            db.add(
                User(
                    org_id=org.id,
                    email=email,
                    name=role.value.title(),
                    role=role,
                    password_hash=hasher.hash("demo1234"),
                )
            )
    for title in ("اللغة العربية", "Biology / الأحياء"):
        subject = db.scalar(
            select(Subject).where(
                Subject.org_id == org.id, Subject.name == title, Subject.grade == "3 ثانوي"
            )
        )
        if subject is None:
            subject = Subject(org_id=org.id, name=title, language=Language.ar, grade="3 ثانوي")
            db.add(subject)
            db.flush()
        for number in range(1, 3):
            chapter = db.scalar(
                select(Chapter).where(Chapter.subject_id == subject.id, Chapter.position == number)
            )
            if chapter is None:
                chapter = Chapter(subject_id=subject.id, title=f"Chapter {number}", position=number)
                db.add(chapter)
                db.flush()
            for lesson_number in range(1, 3):
                lesson = db.scalar(
                    select(Lesson).where(
                        Lesson.chapter_id == chapter.id, Lesson.position == lesson_number
                    )
                )
                if lesson is None:
                    db.add(
                        Lesson(
                            chapter_id=chapter.id,
                            title=f"Lesson {lesson_number}",
                            position=lesson_number,
                        )
                    )
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin")
    admin.add_argument("--org", required=True)
    admin.add_argument("--email", required=True)
    admin.add_argument("--password", required=True)
    admin.add_argument("--name")
    commands.add_parser("seed-dev")
    commands.add_parser("llm-spend")
    prices = commands.add_parser("llm-prices")
    prices.add_argument("--refresh", action="store_true", required=True)
    ping = commands.add_parser("llm-ping")
    ping.add_argument("--model", required=True)
    ping.add_argument("--image")
    args = parser.parse_args()
    if args.command == "llm-prices":
        refresh_prices()
        return
    if args.command == "llm-ping":
        content = [{"type": "text", "text": "Reply briefly with OK."}]
        if args.image:
            content.append(image_part(Path(args.image).read_bytes()))
        result = OpenRouterClient().complete_text(
            stage="verify",
            messages=[{"role": "user", "content": content}],
            org_id=None,
            model_override=args.model,
        )
        print(  # noqa: T201 -- CLI output
            f"Tokens: {result.input_tokens}/{result.output_tokens}; "
            f"cost: ${result.cost_usd}; latency: {result.latency_ms} ms"
        )
        return
    with Session(get_engine()) as db:
        if args.command == "llm-spend":
            print(f"Total: ${total_spend(db)}; this month: ${org_month_spend(db)}")  # noqa: T201
            for group in ("stage", "model"):
                print(f"By {group}: {spend_by(db, group)}")  # noqa: T201
        elif args.command == "seed-dev":
            seed_dev(db)
        else:
            create_admin(db, args.org, args.email, args.password, args.name or args.email)


if __name__ == "__main__":
    main()
