#!/bin/bash
# DevIntel Setup Script

echo "🚀 Setting up DevIntel..."

# OS check
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "⚠️ This script is optimized for macOS with Homebrew."
    echo "Please manually install and start Redis, PostgreSQL, and Neo4j."
    read -p "Press [Enter] to continue after manual installation..."
else
    # Install services using Homebrew
    echo "🍻 Installing services with Homebrew..."
    brew install redis
    brew install postgresql
    brew install neo4j

    # Start services
    echo "🏁 Starting services..."
    brew services start redis
    brew services start postgresql
    brew services start neo4j
fi

# Create the database
echo "🐘 Creating the PostgreSQL database..."
createdb devintel || echo "Database 'devintel' may already exist. Continuing..."

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

# Configure OpenAI API Key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "🔑 OpenAI API Key not found."
    read -p "Please enter your OpenAI API Key: " OPENAI_API_KEY
    export OPENAI_API_KEY
fi


# Initialize DSPy
echo "🤖 Configuring DSPy..."
python -c "import dspy; dspy.settings.configure(lm=dspy.OpenAI(model='gpt-4.1'))"

echo "✅ DevIntel setup complete."
echo "To start the server, run: python server.py"