Telegram bot that allows you to set an expiration time for all new messages in a group 
chat. When the time expires, the bot will automatically delete the messages.

Use the provided Dockerfile to build the bot's image and run it in a container. Pass the
TOKEN environment variable with a valid telegram bot token to the `docker run` command, 
e.g. `docker run -d -e TOKEN=$TOKEN -e DATADIR=/data -v botdb:/data --name bot {image}`.

