# Disable mouse tracking in terminal
# Prevents SGR mouse tracking sequences from being sent to applications
printf '\e[?1000l\e[?1002l\e[?1003l\e[?1006l'
