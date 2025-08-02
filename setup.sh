#!/bin/bash
# DevIntel Setup Script

echo "🚀 Setting up DevIntel..."

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

# Create the database
echo "🐘 Creating the PostgreSQL database..."
createdb devintel

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

# Initialize DSPy
echo "🤖 Configuring DSPy..."
python -c "import dspy; dspy.settings.configure(lm=dspy.OpenAI(model='gpt-4.1'))"

# Start server
echo "🛰️ Starting DevIntel server..."
python server.py