# Dev Machine Simulator

Spins up 3 isolated containers, each acting as a separate developer machine.

## Setup

```bash
cd tools/dev-machines
docker compose build
```

## Usage

Each dev machine needs its own `conduct login`. Open separate terminals:

```bash
# Terminal 1 — Alice
docker compose run --rm dev1 bash
conduct login        # log in as invited developer 1

# Terminal 2 — Bob  
docker compose run --rm dev2 bash
conduct login        # log in as invited developer 2

# Terminal 3 — Carol
docker compose run --rm dev3 bash
conduct login        # log in as invited developer 3
```

After login, run guard sync to register each machine:

```bash
conduct guard sync
```

Each container appears as a separate machine in Guard → Discovery.

## Persistent sessions

Conduct config is stored in named volumes (`dev1-conduct` etc.) so tokens
survive container restarts. To reset a machine:

```bash
docker volume rm dev-machines_dev1-conduct
```

## Cleanup

```bash
docker compose down -v   # removes containers + volumes
