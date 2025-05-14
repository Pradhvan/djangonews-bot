import logging
import os
import sqlite3

import arrow
import discord
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = os.getenv("DISCORD_GUILD")

handler = logging.FileHandler(filename="newsbot.log", encoding="utf-8", mode="w")

# Define the client with message content intent
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

BASE_COMMANDS = [
    "!help",         # Show help text
    "!available",    # List next available volunteering dates
    "!volunteer",    # Assign yourself to a date
    "!unvolunteer",  # Remove yourself from a date
    "!mydates",      # Show dates you've signed up for
    "!status",       # Check status of a specific date
    "!upcoming",     # List upcoming posts and volunteers
]

async def setup_database(db_file="volunteers.db"):
    if not os.path.exists(db_file):
        print(f"'{db_file}' not found. Creating it...")

        # Connect to the SQLite database (it will be created if it doesn't exist)
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # Create the 'volunteers' table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS volunteers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT DEFAULT NULL,
                reminder_date DATE NOT NULL,
                is_taken BOOLEAN DEFAULT FALSE,
                due_date DATE NOT NULL,
                email TEXT DEFAULT NULL,
                status TEXT DEFAULT 'pending',
                timezone TEXT DEFAULT 'UTC'
            )
        """
        )

        # Get the current time for reminder_date and due_date
        now = arrow.utcnow()
        start = now.floor("month")
        end = now.ceil("year").shift(seconds=-1)

        # Insert data into the 'volunteers' table
        current = start
        while current <= end:
            monday = current.shift(weekday=0)  # Monday of current week
            wednesday = monday.shift(days=2)

            # Insert a new record into the 'volunteers' table
            cursor.execute(
                """INSERT INTO volunteers (reminder_date, due_date) VALUES (?, ?)""",
                (
                    monday.format("YYYY-MM-DD"),
                    wednesday.format("YYYY-MM-DD"),
                ),
            )

            # Move to the next week
            current = current.shift(weeks=1)

        # Commit changes and close the connection
        conn.commit()
        print(f"'{db_file}' created with volunteer entries.")
    else:
        print(f"'{db_file}' already exists.")
        print("Connecting to the existing database...")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        print("Connected to the existing database.")
    return cursor


async def setup():
    return await setup_database()


@client.event
async def on_ready():
    print(f"We have logged in as {client.user}")
    cursor = await setup()


async def list_available_date(cursor):
    current_date = arrow.utcnow().format("YYYY-MM-DD")
    rows = cursor.execute(
        """
    SELECT due_date
    FROM volunteers
    WHERE due_date > ?
      AND is_taken = 0
    LIMIT 10
    """,
        (current_date,),
    )

    return rows.fetchall()


@client.event
async def on_message(message):
    conn = sqlite3.connect("volunteers.db")
    cursor = conn.cursor()

    if message.author == client.user:
        return

    if message.content in (BASE_COMMANDS):
        if message.content == "!available":
            rows = await list_available_date(cursor)
            if rows:
                response = "Available dates:\n"
                for row in rows:
                    due_date = arrow.get(row[0]).format("Do MMMM YYYY") 
                    response += f"- {due_date}\n"
                await message.channel.send(response)
            else:
                await message.channel.send("No available dates found.")
        elif message.content in BASE_COMMANDS:
            await message.channel.send(
                f"Hello! We are still working on the code. {message.content} will soon be up and running!"
            )
    else:
        await message.channel.send("I do not understand this command!")


if __name__ == "__main__":
    client.run(TOKEN)
