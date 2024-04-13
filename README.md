# Forward email notifications to signal using signal-cli

This project was built to solve my use case of sending K8S alerts via Signal. Most code was adopted from [LeoVerto/email2signal](https://github.com/LeoVerto/email2signal).

Currently this just means that a container running a Python app listens on port 8025 for incoming emails, extracts the
subject and the email text, and finally utilizes another container running signal-cli ([bbernhard/signal-cli-rest-api](https://github.com/bbernhard/signal-cli-rest-api)) to send a message to a signal number set in the receiver address.

For an example usage see my [nixos-k3s](https://github.com/niki-on-github/nixos-k3s) repository.
