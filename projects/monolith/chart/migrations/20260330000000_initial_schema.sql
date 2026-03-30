-- Create todo schema and tables for the monolith todo app.
CREATE SCHEMA IF NOT EXISTS todo;

CREATE TABLE todo.tasks (
    id SERIAL PRIMARY KEY,
    task TEXT NOT NULL DEFAULT '',
    done BOOLEAN NOT NULL DEFAULT FALSE,
    kind TEXT NOT NULL DEFAULT 'daily',
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE todo.archives (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    content TEXT NOT NULL
);
