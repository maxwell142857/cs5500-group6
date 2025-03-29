#!/bin/bash

# Colors for better output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Dynamic Learning Akinator API Setup ===${NC}"
echo

# Check if Docker is installed and running
echo -e "${YELLOW}Checking if Docker is installed and running...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
    echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Docker daemon is not running. Please start Docker first.${NC}"
    exit 1
fi

echo -e "${GREEN}Docker is installed and running.${NC}"

# Check if docker-compose is installed
echo -e "${YELLOW}Checking if Docker Compose is installed...${NC}"
if ! command -v docker compose &> /dev/null; then
    echo -e "${RED}Docker Compose is not installed. Please install Docker Compose first.${NC}"
    echo "Visit https://docs.docker.com/compose/install/ for installation instructions."
    exit 1
fi

echo -e "${GREEN}Docker Compose is installed.${NC}"

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file...${NC}"
    
    # Prompt for Gemini API key
    read -p "Enter your Google Gemini API key: " gemini_api_key
    
    if [ -z "$gemini_api_key" ]; then
        echo -e "${RED}API key cannot be empty. Please run the script again and provide a valid API key.${NC}"
        exit 1
    fi
    
    # Create .env file
    echo "GEMINI_API_KEY=$gemini_api_key" > .env
    echo -e "${GREEN}.env file created successfully.${NC}"
else
    echo -e "${GREEN}.env file already exists.${NC}"
fi

# Check if the backend directory exists
if [ ! -d "backend" ]; then
    echo -e "${RED}The 'backend' directory does not exist in the current directory.${NC}"
    echo "Please make sure you're running this script from the correct location."
    exit 1
fi

echo -e "${YELLOW}Checking docker-compose.yml file...${NC}"
# Check if docker-compose.yml exists and update it if needed
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${YELLOW}Creating docker-compose.yml file...${NC}"
    cat > docker-compose.yml << 'EOF'
services:
  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - POSTGRES_DB=akinator_db
      - POSTGRES_USER=akinator_user
      - POSTGRES_PASSWORD=password
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=0
      - GEMINI_API=${GEMINI_API_KEY}
      - SESSION_TIMEOUT=3600
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  postgres:
    image: postgres:14
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_DB=akinator_db
      - POSTGRES_USER=akinator_user
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
EOF
    echo -e "${GREEN}docker-compose.yml file created successfully.${NC}"
else
    echo -e "${GREEN}docker-compose.yml file already exists.${NC}"
fi

# Ask user whether to start the services
echo
echo -e "${YELLOW}Do you want to start the services now? (y/n)${NC}"
read -p "" start_services

if [[ $start_services == "y" || $start_services == "Y" ]]; then
    echo -e "${YELLOW}Starting services with docker-compose...${NC}"
    echo -e "${YELLOW}This might take a while for the first time as it needs to download images and build containers.${NC}"
    
    # Start services
    docker compose up --build -d
    
    # Check if services started successfully
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Services started successfully!${NC}"
        echo 
        echo -e "${GREEN}=== Services Information ===${NC}"
        echo -e "API is running at: ${YELLOW}http://localhost:8000${NC}"
        echo -e "API Documentation available at: ${YELLOW}http://localhost:8000/docs${NC}"
        echo
        echo -e "${YELLOW}To view logs:${NC}"
        echo -e "  docker compose logs -f"
        echo
        echo -e "${YELLOW}To stop the services:${NC}"
        echo -e "  docker compose down"
    else
        echo -e "${RED}Failed to start services. Please check the error message above.${NC}"
    fi
else
    echo
    echo -e "${YELLOW}You can start the services later with:${NC}"
    echo -e "  docker compose up --build -d"
    echo
    echo -e "${YELLOW}To view logs:${NC}"
    echo -e "  docker compose logs -f"
    echo
    echo -e "${YELLOW}To stop the services:${NC}"
    echo -e "  docker compose down"
fi

echo
echo -e "${GREEN}Setup complete!${NC}"