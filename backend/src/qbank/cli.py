import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from qbank.auth import hasher
from qbank.config import get_settings
from qbank.db import get_engine
from qbank.models import Chapter, Language, Lesson, Organization, Role, Subject, User


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
    args = parser.parse_args()
    with Session(get_engine()) as db:
        if args.command == "seed-dev":
            seed_dev(db)
        else:
            create_admin(db, args.org, args.email, args.password, args.name or args.email)


if __name__ == "__main__":
    main()
