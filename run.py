from dotenv import load_dotenv
load_dotenv()  # reads .env in this folder (MAIL_*, ANTHROPIC_API_KEY)

from ChatbotWebsite import create_app

# Create the app
app = create_app()

# Run the app
if __name__ == '__main__':
    app.run(debug=True)
