from app import create_app
from app.reminders import register_reminder_commands
from app.waitlist import register_waitlist_commands

app = create_app()
register_reminder_commands(app)
register_waitlist_commands(app)

if __name__ == '__main__':
    app.run(debug=True)
