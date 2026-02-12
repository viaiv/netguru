# Development Dockerfile for NetGuru Frontend
FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy package files first (leverage Docker cache)
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy application code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Run Vite dev server with host flag for Docker
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
