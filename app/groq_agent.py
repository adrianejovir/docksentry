#!/usr/bin/env python3
"""Groq AI Agent - Docker management via natural language."""

import json
import os
import subprocess
import re


SYSTEM_PROMPT = """You are a Docker management assistant. Help users manage their Docker containers and images through natural language.

CURRENT DOCKER STATE:
{state}

Available actions:
- list containers → docker ps -a
- list images → docker images
- stop <container> → docker stop <container>
- start <container> → docker start <container>
- restart <container> → docker restart <container>
- logs <container> → docker logs --tail 30 <container>
- status <container> → docker inspect <container>
- stats → docker stats --no-stream
- pull <image> → docker pull <image>
- remove <container> → docker rm <container> (must be stopped first)

Guidelines:
1. Always confirm before making destructive changes (stop, remove)
2. Don't run commands, output what action would be taken and wait for confirmation
3. Provide clear, concise responses
4. Use emoji appropriately
5. If user says "yes" or "confirm", execute the last pending action"""


def get_docker_state():
    """Get current Docker state for context."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}|{{.Status}}|{{.Image}}"],
            capture_output=True, text=True, timeout=15
        )
        return result.stdout.strip() if result.stdout else "No containers"
    except:
        return "Docker not available"


def run_docker_command(cmd: str) -> str:
    """Execute a docker command and return output."""
    parts = cmd.strip().split()
    if not parts:
        return "No command"
    
    try:
        result = subprocess.run(
            ["docker"] + parts,
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout or result.stderr
        if result.returncode != 0:
            return f"Error: {output}"
        return output.strip() if output.strip() else "Done"
    except subprocess.TimeoutExpired:
        return "Timeout"
    except Exception as e:
        return str(e)


class GroqAgent:
    def __init__(self, api_key: str):
        try:
            from groq import Groq
            self.client = Groq(api_key=api_key)
            self.available = True
        except ImportError:
            self.available = False
            print("GROQ: groq package not installed")
        except Exception as e:
            self.available = False
            print(f"GROQ: init error - {e}")
    
    def chat(self, message: str, confirm_action: str = None) -> str:
        """Process message and return response."""
        if not self.available:
            return "❌ Groq not available"
        
        # Get current state
        state = get_docker_state()
        
        # Build system prompt
        system = SYSTEM_PROMPT.format(state=state)
        
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message}
        ]
        
        if confirm_action:
            messages.append({"role": "system", "content": f"User confirmed. Execute this action: {confirm_action}"})
        
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.3,
                max_tokens=1024
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"❌ API error: {e}"
    
    def extract_command(self, response: str) -> str:
        """Extract docker command from LLM response."""
        # Look for docker commands in response
        match = re.search(r'docker\s+\w+\s+[\w\-./:]+', response)
        if match:
            return match.group(0)
        return None