FROM --platform=linux/amd64 python:3.10

# Install system dependencies for PyMuPDF
RUN apt-get update && apt-get install -y libglib2.0-0 libgl1-mesa-glx

WORKDIR /app

# Copy the processing script
COPY extract.py .

# Install Python dependencies
RUN pip install pymupdf

# Run the script
CMD ["python", "extract.py"] 