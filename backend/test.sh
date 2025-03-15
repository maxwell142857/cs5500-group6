#!/bin/bash
# Testing script for Pure AI-Driven Akinator

# Base URL
API_URL="http://localhost:8000/api"

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored section headers
section() {
    echo -e "\n${BLUE}==== $1 ====${NC}\n"
}

# Function to print colored status messages
status() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print user prompts
prompt() {
    echo -e "${YELLOW}? $1${NC}"
}

# Function to print info messages
info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Main interactive game loop
play_game() {
    section "AI-Driven Akinator Game"
    
    # Ask the user for a domain
    prompt "What kind of thing are you thinking of? (e.g., animal, book, food, etc.)"
    read DOMAIN
    
    info "Starting a new game with domain: $DOMAIN"
    START_RESPONSE=$(curl -s -X POST \
      "${API_URL}/start-game" \
      -H "Content-Type: application/json" \
      -d "{\"domain\": \"$DOMAIN\"}")
    
    echo "$START_RESPONSE"
    
    # Extract session_id and message
    SESSION_ID=$(echo "$START_RESPONSE" | grep -o '"session_id":"[^"]*' | cut -d'"' -f4)
    MESSAGE=$(echo "$START_RESPONSE" | grep -o '"message":"[^"]*' | cut -d'"' -f4)
    
    if [[ -z "$SESSION_ID" ]]; then
        echo -e "${RED}Failed to get session ID. Check if the server is running and AI models are loaded.${NC}"
        return 1
    fi
    
    status "Session ID: $SESSION_ID"
    info "$MESSAGE"
    
    # Main game loop
    SHOULD_GUESS="false"
    QUESTIONS_ASKED=0
    
    while [[ "$SHOULD_GUESS" != "true" ]] && (( QUESTIONS_ASKED < 20 )); do
        echo -e "\n${YELLOW}Question round $((QUESTIONS_ASKED + 1))${NC}"
        
        # Get a question - this will be AI-generated
        echo "Getting next question..."
        QUESTION_RESPONSE=$(curl -s "${API_URL}/get-question/$SESSION_ID")
        echo "$QUESTION_RESPONSE"
        
        # Extract question details
        QUESTION_ID=$(echo "$QUESTION_RESPONSE" | grep -o '"question_id":[^,}]*' | cut -d':' -f2)
        QUESTION_TEXT=$(echo "$QUESTION_RESPONSE" | grep -o '"question":"[^"]*' | cut -d'"' -f4)
        SHOULD_GUESS=$(echo "$QUESTION_RESPONSE" | grep -o '"should_guess":[^,}]*' | cut -d':' -f2)
        
        if [[ "$SHOULD_GUESS" == "true" ]]; then
            info "Ready to make a guess"
            break
        fi
        
        if [[ -z "$QUESTION_ID" || -z "$QUESTION_TEXT" ]]; then
            echo -e "${RED}Failed to get question details${NC}"
            return 1
        fi
        
        # Ask user for answer
        prompt "Q: $QUESTION_TEXT (yes/no)"
        read ANSWER
        
        # Normalize answer
        ANSWER=$(echo "$ANSWER" | tr '[:upper:]' '[:lower:]')
        if [[ "$ANSWER" != "yes" && "$ANSWER" != "no" && "$ANSWER" != "y" && "$ANSWER" != "n" ]]; then
            info "Please answer 'yes' or 'no'. Defaulting to 'no'."
            ANSWER="no"
        fi
        
        # Submit the answer
        ANSWER_RESPONSE=$(curl -s -X POST \
          "${API_URL}/submit-answer" \
          -H "Content-Type: application/json" \
          -d "{\"session_id\": \"$SESSION_ID\", \"question_id\": $QUESTION_ID, \"answer\": \"$ANSWER\"}")
        
        echo "$ANSWER_RESPONSE"
        
        # Check if we should make a guess
        SHOULD_GUESS=$(echo "$ANSWER_RESPONSE" | grep -o '"should_guess":[^,}]*' | cut -d':' -f2)
        QUESTIONS_ASKED=$((QUESTIONS_ASKED + 1))
        
        # Show top entities if we have any
        TOP_ENTITIES=$(echo "$ANSWER_RESPONSE" | grep -o '"top_entities":\[[^]]*\]' | sed 's/"entity":/entity:/g' | sed 's/"probability":/probability:/g')
        if [[ ! -z "$TOP_ENTITIES" && "$TOP_ENTITIES" != "[]" ]]; then
            info "Current top guesses: $TOP_ENTITIES"
        fi
    done
    
    # Learning mode vs. guessing mode
    if [[ "$MESSAGE" == *"don't know any"* ]]; then
        # Learning mode - ask user what they were thinking of
        section "Learning Mode Complete"
        prompt "What ${DOMAIN} were you thinking of?"
        read ENTITY_NAME
        
        info "Thank you! Adding $ENTITY_NAME to my knowledge base."
        RESULT_RESPONSE=$(curl -s -X POST \
          "${API_URL}/submit-result" \
          -H "Content-Type: application/json" \
          -d "{\"session_id\": \"$SESSION_ID\", \"was_correct\": false, \"actual_entity\": \"$ENTITY_NAME\", \"entity_type\": \"$DOMAIN\"}")
        
        echo "$RESULT_RESPONSE"
        status "I've learned about $ENTITY_NAME! Play again to see if I can guess it next time."
    else
        # Guessing mode - make a guess
        section "Making Final Guess"
        GUESS_RESPONSE=$(curl -s "${API_URL}/make-guess/$SESSION_ID")
        echo "$GUESS_RESPONSE"
        
        # Extract guess
        GUESS=$(echo "$GUESS_RESPONSE" | grep -o '"guess":"[^"]*' | cut -d'"' -f4)
        CONFIDENCE=$(echo "$GUESS_RESPONSE" | grep -o '"confidence":[^,}]*' | cut -d':' -f2)
        
        info "I think it's a: ${YELLOW}$GUESS${NC} (confidence: $CONFIDENCE)"
        prompt "Am I correct? (yes/no)"
        read IS_CORRECT
        
        # Normalize answer
        IS_CORRECT=$(echo "$IS_CORRECT" | tr '[:upper:]' '[:lower:]')
        if [[ "$IS_CORRECT" == "yes" || "$IS_CORRECT" == "y" ]]; then
            # Submit correct result
            status "Great! I guessed correctly."
            RESULT_RESPONSE=$(curl -s -X POST \
              "${API_URL}/submit-result" \
              -H "Content-Type: application/json" \
              -d "{\"session_id\": \"$SESSION_ID\", \"was_correct\": true}")
        else
            # Submit incorrect result
            prompt "What were you actually thinking of?"
            read ACTUAL_ENTITY
            
            info "I'll remember that for next time!"
            RESULT_RESPONSE=$(curl -s -X POST \
              "${API_URL}/submit-result" \
              -H "Content-Type: application/json" \
              -d "{\"session_id\": \"$SESSION_ID\", \"was_correct\": false, \"actual_entity\": \"$ACTUAL_ENTITY\", \"entity_type\": \"$DOMAIN\"}")
        fi
        
        echo "$RESULT_RESPONSE"
    fi
    
    # Ask if user wants to play again
    prompt "Would you like to play again? (yes/no)"
    read PLAY_AGAIN
    
    # Normalize answer
    PLAY_AGAIN=$(echo "$PLAY_AGAIN" | tr '[:upper:]' '[:lower:]')
    if [[ "$PLAY_AGAIN" == "yes" || "$PLAY_AGAIN" == "y" ]]; then
        play_game
    else
        section "Thanks for playing!"
    fi
}

# Start the game
play_game