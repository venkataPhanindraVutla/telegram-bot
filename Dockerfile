# Use an official Python runtime as a parent image and name the stage "builder"
FROM python:3.11-slim AS builder

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container
COPY . .

# Set the command to run the application.
# The main.py script will now handle starting the web server.
CMD ["python3", "main.py"]
