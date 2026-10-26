# ═══════════════════════════════════════════════════════════
#  Project Phoenix — Frontend Dockerfile (Nginx Alpine)
#  Serves static citizen portal at edge speeds
# ═══════════════════════════════════════════════════════════

FROM nginx:alpine

# Copy static frontend assets into standard nginx document root
COPY . /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
