#!/bin/sh

set -e

echo "Fetching latest code..."
git fetch origin

echo "Pulling latest main into current branch..."
git pull origin main

echo "Adding all changes..."
git add .

echo "Enter commit message:"
read commit_message

if [ -z "$commit_message" ]; then
  echo "Commit message cannot be empty."
  exit 1
fi

echo "Committing changes..."
git commit -m "$commit_message"

echo "Pushing current branch..."
git push origin HEAD

echo "Done."