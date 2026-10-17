#pragma once
#include <string>
struct sqlite3;
namespace competitive {
// Separate SQLite journal: game DB contention must not discard round results.
// Ordered sequence + the game DB's unique EventID make replay after a crash safe.
struct PendingResult {std::string event;int winner=0,loser=0;std::string reason;};
void initializeOutbox(sqlite3* db);
void enqueue(sqlite3* db,const PendingResult& result);
bool oldest(sqlite3* db,PendingResult& result);
void acknowledge(sqlite3* db,const std::string& event);
}