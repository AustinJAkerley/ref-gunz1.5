// Native isolated tests; argv[1] MUST be a fresh disposable directory.
// g++ -std=c++14 economy.cpp economy_tests.cpp -lsqlite3 -o /tmp/economy-tests
// Run with a newly created temporary directory, NEVER a game/runtime path.
#include "economy.hpp"
#include "sqlite3.h"
#include <climits>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace ec = competitive::economy;
namespace {
int checks = 0;
void check(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
void sql(sqlite3* db, const char* text) {
    char* error = nullptr;
    if (sqlite3_exec(db, text, nullptr, nullptr, &error) != SQLITE_OK) {
        const std::string message = error ? error : sqlite3_errmsg(db);
        sqlite3_free(error); throw std::runtime_error(message);
    }
}
class DB {
    sqlite3* value_ = nullptr;
public:
    explicit DB(const std::string& path = ":memory:") {
        if (sqlite3_open(path.c_str(), &value_) != SQLITE_OK) throw std::runtime_error("open test db");
        sqlite3_busy_timeout(value_, 0);
    }
    ~DB() { sqlite3_close(value_); }
    operator sqlite3*() const { return value_; }
};
long long number(sqlite3* db, const char* text) {
    sqlite3_stmt* stmt = nullptr;
    if (sqlite3_prepare_v2(db, text, -1, &stmt, nullptr) != SQLITE_OK) throw std::runtime_error(sqlite3_errmsg(db));
    const int rc = sqlite3_step(stmt);
    const auto value = rc == SQLITE_ROW ? sqlite3_column_int64(stmt, 0) : 0;
    sqlite3_finalize(stmt);
    if (rc != SQLITE_ROW) throw std::runtime_error("missing test row");
    return value;
}
template<class F> void fails(F f, const char* message) {
    bool threw = false;
    try { f(); } catch (const std::exception&) { threw = true; }
    check(threw, message);
}
void schema(sqlite3* db) {
    sql(db, "CREATE TABLE Character(CID INTEGER PRIMARY KEY,AID INTEGER NOT NULL,BP INTEGER NOT NULL,XP INTEGER NOT NULL DEFAULT 1101991900,Level INTEGER NOT NULL DEFAULT 99,DeleteFlag INTEGER DEFAULT 0,KillCount INTEGER DEFAULT 0,DeathCount INTEGER DEFAULT 0)");
    sql(db, "CREATE TABLE DuelRating(CID INTEGER PRIMARY KEY,Elo INTEGER NOT NULL DEFAULT 1000 CHECK(Elo>=0))");
    sql(db, "CREATE TABLE CharacterItem(CIID INTEGER PRIMARY KEY,CID INTEGER,ItemID INTEGER,RegDate TEXT)");
    sql(db, "INSERT INTO Character(CID,AID,BP) VALUES(1,101,1000),(2,202,300),(3,101,800),(4,404,500)");
    ec::initialize(db);
}
ec::Player one() { return {1, 101, 1, false, false, true}; }
ec::Player two() { return {2, 202, 2, false, false, true}; }
ec::Kill duel() { return {one(), two(), true, true, true, true, false, true}; }
// Preserve the previous persistence suite as migration coverage for already
// journaled 10..15 rewards. Production Match::kill only emits amount=0 now.
std::vector<ec::Event> legacyKill(ec::Match& match, const ec::Kill& kill, int amount) {
    auto events = match.kill(kill);
    for (auto& event : events) event.amount = amount;
    return events;
}
void apply(sqlite3* db, const std::vector<ec::Event>& events) {
    for (const auto& e : events) ec::record(db, e);
}
ec::Match start(sqlite3* db, const std::string& id) {
    ec::Match m; apply(db, m.begin(id)); apply(db, m.join(one())); apply(db, m.join(two())); return m;
}
int drain(sqlite3* db, sqlite3* journal) {
    ec::Event e; int count = 0;
    while (ec::oldest(journal, e)) {
        ec::record(db, e); ec::acknowledge(journal, e.id); ++count;
    }
    return count;
}
void queue(sqlite3* journal, const std::vector<ec::Event>& events) {
    for (const auto& e : events) ec::enqueue(journal, e);
}
void eligibility() {
    auto k = duel(); check(ec::eligible(k), "legitimate player kill");
    k.attacker = k.victim; check(!ec::eligible(k), "suicide rejected");
    k = duel(); k.teamGame = true; k.victim.team = k.attacker.team;
    check(!ec::eligible(k), "team kill rejected");
    k.teamGame = false; check(ec::eligible(k), "FFA equal team enum is not team kill");
    k = duel(); k.attacker.bot = true; check(!ec::eligible(k), "bot attacker");
    k = duel(); k.victim.bot = true; check(!ec::eligible(k), "bot victim");
    k = duel(); k.victim.aid = k.attacker.aid; check(!ec::eligible(k), "same account");
    k = duel(); k.attacker.cid = 0; check(!ec::eligible(k), "invalid CID");
    k = duel(); k.victim.aid = 0; check(!ec::eligible(k), "invalid account");
    k = duel(); k.victimAlive = false; check(!ec::eligible(k), "duplicate dead notification");
    k = duel(); k.playing = false; check(!ec::eligible(k), "countdown/end not play");
    k = duel(); k.allowedMode = false; check(!ec::eligible(k), "practice/quest excluded");
    k = duel(); k.sameStage = false; check(!ec::eligible(k), "cross stage");
    k = duel(); k.activeDuelPair = false; check(!ec::eligible(k), "Duel wait queue excluded");
    k = duel(); k.attacker.inBattle = false; check(!ec::eligible(k), "attacker outside battle");
    k = duel(); k.victim.inBattle = false; check(!ec::eligible(k), "victim outside battle");
    k = duel(); k.attacker.spectator = true; check(!ec::eligible(k), "observer attacker");
    k = duel(); k.victim.spectator = true; check(!ec::eligible(k), "observer victim");
}
void eloRewards() {
    check(ec::killReward(1000, 1000) == 15 && ec::killReward(INT_MAX, INT_MAX) == 15,
        "equal Elo pays exactly 15");
    check(ec::killReward(3000, 0) == 10 && ec::killReward(0, 3000) == 20,
        "large Elo gaps reach both inclusive limits");
    check(ec::killReward(INT_MIN, INT_MAX) == 20 && ec::killReward(INT_MAX, INT_MIN) == 10,
        "int subtraction and power cannot overflow");
    check(ec::killReward(1400, 1000) == 11 && ec::killReward(1000, 1400) == 19,
        "stronger victim pays more, weaker victim pays less");
    int previousVictim = 10, previousAttacker = 20;
    bool seen[11]{};
    for (int rating = 0; rating <= 10000; ++rating) {
        const int victim = ec::killReward(1000, rating), attacker = ec::killReward(rating, 1000);
        check(victim >= 10 && victim <= 20 && attacker >= 10 && attacker <= 20, "bounded reward sweep");
        check(victim >= previousVictim && attacker <= previousAttacker, "monotonic opponent/self Elo sweep");
        check(victim == int(std::round(10 + 10 / (1 + std::pow(10.0, (1000.0 - rating) / 400)))),
            "reward matches proposed rounded formula");
        seen[victim - 10] = true; previousVictim = victim; previousAttacker = attacker;
    }
    for (bool value : seen) check(value, "all eleven inclusive awards reachable");

    DB db; schema(db);
    check(ec::killReward(db, 1, 2) == 15 && ec::killReward(db, 999, 999) == 15,
        "missing rating rows default independently to 1000, including same CID");
    sql(db, "INSERT INTO DuelRating(CID,Elo) VALUES(1,1400)");
    check(ec::killReward(db, 1, 2) == 11 && ec::killReward(db, 2, 1) == 19,
        "one missing rating uses default, not a missing join or zero");
    check(ec::killReward(db, 1, 1) == 15, "same stored CID lookup returns equal reward");
    sql(db, "INSERT INTO DuelRating(CID,Elo) VALUES(2,3000)");
    check(ec::killReward(db, 1, 2) == 20 && ec::killReward(db, 2, 1) == 10, "server stored rating lookup");
    check(number(db, "SELECT COUNT(*) FROM DuelRating") == 2, "lookup never inserts or changes ratings");
    sql(db, "DROP TABLE DuelRating");
    fails([&] { ec::killReward(db, 1, 2); }, "SQL failure is not treated as a missing rating row");
}
void accounting() {
    DB db; schema(db);
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000, "initial wallet preserved");
    ec::initialize(db);
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000, "migration rerun preserves BP");
    auto m = start(db, "whole-match");
        auto first = legacyKill(m, duel(), 10), second = legacyKill(m, duel(), 15);
        check(!ec::record(db, legacyKill(m, duel(), 9).front()).applied &&
            !ec::record(db, legacyKill(m, duel(), 16).front()).applied, "invalid legacy payloads rejected");
    apply(db, first); apply(db, second); // Two Duel rounds, one match.
    check(ec::earned(db, m.id(), 1) == 25, "Duel rounds accumulate in one match");
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1025, "only kill reward before finish");
    check(ec::record(db, first.front()).replay, "same kill event id replay");
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1025, "replay not paid twice");
    auto collision = first.front(); collision.amount = 11;
    fails([&] { ec::record(db, collision); }, "different payload cannot reuse ID");
    auto finish = m.finish({one(), two()}); apply(db, finish);
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1037, "floor(25/2), NOT floor(wallet/2)");
    check(number(db, "SELECT BP FROM Character WHERE CID=2") == 300, "zero earnings zero bonus");
    check(ec::earned(db, m.id(), 1) == 25 && ec::rewardTotal(db, 1) == 37, "scoreboard excludes bonus");
    check(m.finish({one(), two()}).empty(), "double completion generates no events");
    apply(db, finish);
    auto alternate = finish.front(); alternate.id = "alternate-completion";
    check(!ec::record(db, alternate).applied, "different finish ID cannot duplicate match completion");
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1037, "all completion replays unchanged");
    check(m.kill(duel()).empty(), "post-finish kill excluded");
    check(number(db, "SELECT XP FROM Character WHERE CID=1") == 1101991900 &&
          number(db, "SELECT Level FROM Character WHERE CID=1") == 99, "XP never converted or rewarded");
    auto next = start(db, "next-match"); apply(db, legacyKill(next, duel(), 11)); apply(db, next.finish({one(), two()}));
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1053, "new match bonus excludes previous earnings");
}
void leaving() {
    DB db; schema(db);
    auto m = start(db, "leave"); apply(db, legacyKill(m, duel(), 15));
    apply(db, m.leave(one())); check(m.leave(one()).empty(), "double leave no event");
    check(m.join(one()).empty(), "reconnect cannot replace membership tombstone");
    apply(db, legacyKill(m, duel(), 10)); // Rejoined player can earn kills, but no bonus.
    apply(db, m.finish({one(), two()}));
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1025, "leave forfeits entire completion bonus");
    auto absent = start(db, "not-present"); apply(db, legacyKill(absent, duel(), 15)); apply(db, absent.finish({two()}));
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1040, "must remain at finish");
    auto observer = start(db, "spectate"); apply(db, legacyKill(observer, duel(), 15));
    auto p = one(); p.spectator = true; apply(db, observer.finish({p, two()}));
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1055, "spectator no completion");
    auto loading = start(db, "loading-leave"); p = one(); p.inBattle = false;
    apply(db, loading.leave(p)); apply(db, legacyKill(loading, duel(), 15)); apply(db, loading.finish({one(), two()}));
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1070, "loading leave persists disqualification");
    auto abort = start(db, "abort"); apply(db, legacyKill(abort, duel(), 10)); apply(db, abort.abort());
    check(abort.finish({one(), two()}).empty(), "destroy/abort never completion");
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1080, "aborted match retains only kills");
    auto forged = start(db, "left-ledger"); apply(db, legacyKill(forged, duel(), 15)); apply(db, forged.leave(one()));
    ec::Event finish{"forged-finish", forged.id(), ec::Kind::Finish, 1, 101};
    check(ec::record(db, finish).credited == 0, "DB also enforces leave disqualification");
}
void validity() {
    DB db; schema(db); auto m = start(db, "invalid");
    auto event = m.kill(duel()).front();
    event.id = "same-cid"; event.victim = event.cid; event.victimAid = 202;
    check(!ec::record(db, event).applied, "same CID cannot earn despite equal-rating lookup");
    event.id = "same-account"; event.victim = 3; event.victimAid = 101;
    check(!ec::record(db, event).applied, "DB rejects same-account pair");
    event.id = "bad-aid"; event.victim = 2; event.victimAid = 999;
    check(!ec::record(db, event).applied, "DB verifies character-account association");
    event.id = "missing"; event.victim = 999; event.victimAid = 999;
    check(!ec::record(db, event).applied, "DB rejects nonexistent character");
    event.id = "unjoined"; event.victim = 4; event.victimAid = 404;
    check(!ec::record(db, event).applied, "DB rejects absent membership");
    event.id = "deleted"; event.victim = 4; event.victimAid = 404;
    sql(db, "UPDATE Character SET DeleteFlag=1 WHERE CID=4");
    check(!ec::record(db, event).applied, "DB rejects deleted victim without accepted membership");
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000, "invalid rewards never modify BP");
}
void fabricatedMembers() {
    // A durable Join is not permission to invent a CID/AID association, even
    // when the real character has subsequently been soft-deleted.
    for (bool deleted : {false, true}) {
        for (const auto& victim : std::vector<ec::Player>{{2, 999, 2, false, false, true},
                                                       {999, 202, 2, false, false, true}}) {
            DB db, out; schema(db); ec::initializeJournal(out);
            if (deleted) sql(db, "UPDATE Character SET DeleteFlag=1 WHERE CID=2");
            ec::Match m; queue(out, m.begin("fabricated-member")); queue(out, m.join(one()));
            queue(out, m.join(victim));
            auto k = duel(); k.victim = victim;
            queue(out, m.kill(k)); queue(out, m.finish({one(), victim}));
            check(drain(db, out) == 7, "fabricated membership events are consumed without reward");
            check(number(db, "SELECT COUNT(*) FROM GBucksParticipant") == 1,
                "nonexistent CID or mismatched AID cannot create accepted membership");
            check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000 &&
                ec::earned(db, m.id(), 1) == 0 && ec::rewardTotal(db, 1) == 0,
                "fabricated member cannot yield kill or completion earnings");
            check(number(db, "SELECT SUM(Credited) FROM GBucksEvent") == 0,
                "fabricated member events record zero credited rewards");
        }
    }
}
void transactionsAndCache() {
    DB db, journal; schema(db); ec::initializeJournal(journal);
    auto m = start(db, "rollback"); const auto event = legacyKill(m, duel(), 15).front();
    int wallet = 1000; long long applied = 0;
    queue(journal, {event});
    // Failure AFTER BP update, inside the actual ledger transaction.
    sql(db, "CREATE TRIGGER FailCredit BEFORE UPDATE ON GBucksParticipant WHEN NEW.KillEarned>OLD.KillEarned BEGIN SELECT RAISE(ABORT,'injected ledger failure'); END");
    fails([&] { drain(db, journal); }, "mid-transaction error surfaces");
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000, "BP rolled back with ledger");
    check(ec::earned(db, m.id(), 1) == 0 && ec::rewardTotal(db, 1) == 0, "ledger and total rolled back");
    check(number(journal, "SELECT COUNT(*) FROM PendingGBucks") == 1, "failed event remains journaled");
    check(!ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1)) && wallet == 1000, "failed reward never enters cache");
    check(number(db, "SELECT COUNT(*) FROM GBucksEvent WHERE Kind=4") == 0, "failure leaves no idempotence marker");
    sql(db, "DROP TRIGGER FailCredit"); check(drain(db, journal) == 1, "retry after failure commits");
    check(ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1)) && wallet == 1015, "cache changes after commit");
    check(!ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1)), "repeat sync no double cache credit");

    // Same SQL debit+inventory transaction used by SQLiteDatabase::BuyBountyItem.
    sql(db, "BEGIN TRANSACTION; UPDATE Character SET BP=BP-200 WHERE CID=1; INSERT INTO CharacterItem(CID,ItemID,RegDate) VALUES(1,700,'test'); COMMIT");
    wallet -= 200;
    check(wallet == number(db, "SELECT BP FROM Character WHERE CID=1"), "committed GBucks spend from original BP wallet");
    const auto next = legacyKill(m, duel(), 11).front();
    ec::record(db, next); ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1));
    check(wallet == 826 && number(db, "SELECT BP FROM Character WHERE CID=1") == 826, "reward after purchase preserves debit");
    // Unrelated legacy cached debit must not be overwritten by a DB snapshot.
    wallet -= 50; int cachedBP = -50;
    const auto later = legacyKill(m, duel(), 10).front(); ec::record(db, later);
    ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1));
    check(wallet == 786 && cachedBP == -50, "sync preserves pending non-economy debit");
    sql(db, "UPDATE Character SET BP=BP-50,KillCount=KillCount+1 WHERE CID=1"); cachedBP = 0;
    check(wallet == number(db, "SELECT BP FROM Character WHERE CID=1") && cachedBP == 0, "cache flush cannot duplicate rewards");

    const auto commitFail = legacyKill(m, duel(), 14).front(); queue(journal, {commitFail});
    sqlite3_commit_hook(db, [](void*) -> int { return 1; }, nullptr);
    fails([&] { drain(db, journal); }, "actual COMMIT failure");
    sqlite3_commit_hook(db, nullptr, nullptr);
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 786, "COMMIT failure rolled back wallet");
    check(!ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1)), "COMMIT failure cache unchanged");
    check(drain(db, journal) == 1, "COMMIT failure retries successfully");
    ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1)); check(wallet == 800, "COMMIT retry paid once");

    // Crash window: game COMMIT succeeded, journal ACK did not.
    const auto ackFail = legacyKill(m, duel(), 13).front(); queue(journal, {ackFail});
    sql(journal, "CREATE TRIGGER FailAck BEFORE DELETE ON PendingGBucks BEGIN SELECT RAISE(ABORT,'ack failure'); END");
    fails([&] { drain(db, journal); }, "ACK failure after real game commit");
    ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1)); check(wallet == 813, "committed but unacked reward visible");
    sql(journal, "DROP TRIGGER FailAck"); check(drain(db, journal) == 1, "unacked replay consumed");
    check(!ec::syncWallet(wallet, applied, ec::rewardTotal(db, 1)) && wallet == 813, "unacked replay no duplicate");
    queue(journal, {event}); auto conflict = event; conflict.amount = 10;
    fails([&] { queue(journal, {conflict}); }, "journal rejects event ID collision");
    drain(db, journal);
}
void limits() {
    DB db; schema(db); auto m = start(db, "overflow");
    sql(db, "UPDATE Character SET BP=2147483640 WHERE CID=1");
    const auto e = m.kill(duel()).front();
    fails([&] { ec::record(db, e); }, "wallet overflow retries rather than wraps");
    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 2147483640, "overflow preserves wallet");
    check(ec::rewardTotal(db, 1) == 0, "overflow no partial ledger");
    sql(db, "UPDATE Character SET BP=BP-100 WHERE CID=1");
    check(ec::record(db, e).credited == 15, "spending unblocks queued overflow");
    int bp = INT_MAX; long long watermark = 0;
    fails([&] { ec::syncWallet(bp, watermark, 10); }, "live int overflow fails closed");
    check(bp == INT_MAX && watermark == 0, "overflow sync not partially applied");
    bp = 50; watermark = 20;
    fails([&] { ec::syncWallet(bp, watermark, 19); }, "watermark regression rejected");
}
void settlementPersistence(const std::string& directory) {
    const auto game = directory + "/elo-settlement-game.sqlite";
    const auto journal = directory + "/elo-settlement-journal.sqlite";
    for (const auto& path : {game, journal}) {
        auto* f = std::fopen(path.c_str(), "rb");
        if (f) { std::fclose(f); throw std::runtime_error("Refusing existing test database"); }
    }
    ec::Event kill;
    {
        DB db(game), out(journal), blocker(game); schema(db); ec::initializeJournal(out);
        auto m = start(db, "elo-settlement");
        sql(blocker, "BEGIN EXCLUSIVE");
        kill = m.kill(duel()).front(); queue(out, {kill});
        check(kill.amount == 0, "accepted kill queues with no game DB read or random amount");
        fails([&] { drain(db, out); }, "game lock delays settlement without dropping generated kill");
        check(number(out, "SELECT COUNT(*) FROM PendingGBucks") == 1, "zero-amount event durable during game lock");
        sql(blocker, "ROLLBACK");
        sql(db, "DROP TABLE DuelRating");
        fails([&] { drain(db, out); }, "rating SQL failure retains pending reward");
        check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000 &&
              number(db, "SELECT COUNT(*) FROM GBucksEvent WHERE Kind=4") == 0,
            "rating failure rolls back wallet and event marker");
        sql(db, "CREATE TABLE DuelRating(CID INTEGER PRIMARY KEY,Elo INTEGER NOT NULL DEFAULT 1000);"
                "INSERT INTO DuelRating VALUES(1,1000),(2,1400)");
        sqlite3_commit_hook(db, [](void*) -> int { return 1; }, nullptr);
        fails([&] { drain(db, out); }, "computed Elo reward rolls back on COMMIT failure");
        sqlite3_commit_hook(db, nullptr, nullptr);
        check(ec::earned(db, kill.match, 1) == 0 && ec::rewardTotal(db, 1) == 0 &&
              number(db, "SELECT BP FROM Character WHERE CID=1") == 1000, "failed first commit freezes no award");
        sql(db, "UPDATE DuelRating SET Elo=600 WHERE CID=2");
        sql(out, "CREATE TRIGGER FailAck BEFORE DELETE ON PendingGBucks BEGIN SELECT RAISE(ABORT,'ack failure'); END");
        fails([&] { drain(db, out); }, "computed reward commits even when journal ACK fails");
        check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1011 &&
              ec::earned(db, kill.match, 1) == 11 && ec::rewardTotal(db, 1) == 11,
            "first successful commit uses then-current recorded Elo");
        check(number(db, "SELECT Amount FROM GBucksEvent WHERE Kind=4") == 0 &&
              number(db, "SELECT Credited FROM GBucksEvent WHERE Kind=4") == 11,
            "original zero payload and computed credited award persist separately");
        sql(db, "UPDATE DuelRating SET Elo=3000 WHERE CID=2");
        sql(out, "DROP TRIGGER FailAck");
        // Restart with changed ratings and an unacknowledged committed kill.
    }
    {
        DB db(game), out(journal); ec::initialize(db); ec::initializeJournal(out);
        const auto replay = ec::record(db, kill);
        check(replay.replay && !replay.applied && replay.credited == 0, "replay reports no newly credited amount");
        check(drain(db, out) == 1 && ec::rewardTotal(db, 1) == 11 && ec::earned(db, kill.match, 1) == 11,
            "restart replay never reprices award against changed Elo");
        auto collision = kill; collision.amount = 11;
        fails([&] { ec::record(db, collision); }, "stored reward cannot replace the original zero event payload");
        ec::Event later{"elo-settlement:later", kill.match, ec::Kind::Kill, 1, 101, 2, 202, 0};
        check(ec::record(db, later).credited == 20, "new event uses new ratings instead of old snapshot");
        ec::Event finish{"elo-settlement:finish", kill.match, ec::Kind::Finish, 1, 101};
        check(ec::record(db, finish).credited == 15, "bonus floors half of committed Elo kill earnings");
        check(ec::earned(db, kill.match, 1) == 31 && ec::rewardTotal(db, 1) == 46 &&
              number(db, "SELECT BP FROM Character WHERE CID=1") == 1046,
            "computed reward, persisted totals, bonus and wallet agree after restart");
        sql(db, "DROP TABLE DuelRating");
        check(ec::record(db, kill).replay && ec::record(db, finish).replay,
            "committed replay never consults ratings, even if rating lookup is unavailable");
    }
}
void notifications() {
    DB db, out; schema(db); ec::initializeJournal(out);
    auto m = start(db, "notifications");
    ec::RewardNotifications notices;
    const std::map<int, std::uint64_t> online{{1, 100}, {2, 200}};
    const std::set<int> ready{1, 2};
    const auto kill = m.kill(duel()).front(); queue(out, {kill});
    auto settle = [&] {
        ec::Event event;
        while (ec::oldest(out, event)) {
            const auto result = ec::record(db, event);
            notices.committed(event, result, 100); // Same ordering as adapter.
            ec::acknowledge(out, event.id);
        }
    };
    sqlite3_commit_hook(db, [](void*) -> int { return 1; }, nullptr);
    fails(settle, "failed COMMIT cannot reach notification staging");
    sqlite3_commit_hook(db, nullptr, nullptr);
    check(notices.take(online, ready).empty(), "no optimistic HUD notice on failed commit");
    sql(out, "CREATE TRIGGER FailAck BEFORE DELETE ON PendingGBucks BEGIN SELECT RAISE(ABORT,'ack failure'); END");
    fails(settle, "ACK failure occurs after notice staging");
    check(notices.take(online, {}).empty(), "notice waits for wallet sync and inventory readiness");
    int bp = 1000; long long total = 0;
    check(ec::syncWallet(bp, total, ec::rewardTotal(db, 1)) && bp == 1015,
        "committed wallet synchronized before popup consumption");
    auto delivery = notices.take(online, ready);
    check(delivery.size() == 1 && delivery[0].cid == 1 && delivery[0].amount == 15 && !delivery[0].completion,
        "one kill HUD notice uses actual committed result");
    fails(settle, "repeated ACK failure replays committed result");
    check(notices.take(online, ready).empty(), "ACK retry cannot duplicate a consumed popup");
    sql(out, "DROP TRIGGER FailAck"); settle();
    check(ec::rewardTotal(db, 1) == 15 && notices.take(online, ready).empty(), "ACK success never requeues replay");

    const auto second = m.kill(duel()).front(); const auto result = ec::record(db, second);
    notices.committed(second, result, 100); notices.committed(second, result, 100);
    check(notices.take(online, {}).empty(), "pending EventID dedup survives deferred wallet sync");
    check(notices.take({{1, 101}, {2, 200}}, ready).empty(), "reconnected same CID cannot receive previous session popup");
    check(notices.take(online, ready).empty(), "replaced session notice permanently discarded");
    const auto offline = m.kill(duel()).front(); notices.committed(offline, ec::record(db, offline), 0);
    check(notices.take(online, ready).empty(), "offline credit is never replayed on login");
    notices.committed(offline, ec::record(db, offline), 100);
    check(notices.take(online, ready).empty(), "login replay of old committed event creates no popup");
    const auto disconnected = m.kill(duel()).front(); notices.committed(disconnected, ec::record(db, disconnected), 100);
    check(notices.take({}, ready).empty() && notices.take(online, ready).empty(), "disconnect drops pending notification");

    const auto sendFailure = m.kill(duel()).front(); queue(out, {sendFailure}); settle();
    check(number(out, "SELECT COUNT(*) FROM PendingGBucks") == 0, "reward journal ACK independent of HUD send");
    ec::syncWallet(bp, total, ec::rewardTotal(db, 1));
    delivery = notices.take(online, ready);
    check(delivery.size() == 1 && bp == 1075, "wallet includes all five rewards including offline credit");
    int sends = 0;
    for (const auto& notice : delivery) {
        try { ++sends; throw std::runtime_error(std::to_string(notice.amount)); }
        catch (const std::exception&) {} // Adapter catches callback failures separately.
    }
    notices.committed(sendFailure, ec::record(db, sendFailure), 100);
    check(sends == 1 && notices.take(online, ready).empty() && ec::rewardTotal(db, 1) == 75,
        "failed or ambiguous HUD send never retries or undoes durable money");

    queue(out, m.finish({one(), two()})); settle(); ec::syncWallet(bp, total, ec::rewardTotal(db, 1));
    delivery = notices.take(online, ready);
    check(delivery.size() == 1 && delivery[0].completion && delivery[0].amount == 37 && bp == 1112,
        "completion uses credited bonus and flag; zero bonus and close never notify");
    ec::RewardNotifications restarted;
    restarted.committed(kill, ec::record(db, kill), 100);
    check(restarted.take(online, ready).empty(), "fresh process/session does not recreate historical popup");
}
void durable(const std::string& directory) {
    const auto game = directory + "/economy-test-game.sqlite";
    const auto journal = directory + "/economy-test-journal.sqlite";
    for (const auto& path : {game, journal}) {
        auto* f = std::fopen(path.c_str(), "rb");
        if (f) { std::fclose(f); throw std::runtime_error("Refusing existing test database"); }
    }
    {
        DB db(game), out(journal), blocker(game), journalBlocker(journal); schema(db); ec::initializeJournal(out);
        ec::Match m; const auto begin = m.begin("durable");
        sql(journalBlocker, "BEGIN IMMEDIATE");
        fails([&] { queue(out, begin); }, "journal lock fails before acknowledgement");
        check(number(out, "SELECT COUNT(*) FROM PendingGBucks") == 0, "failed journal insertion is atomic");
        sql(journalBlocker, "ROLLBACK");
        queue(out, begin); // Caller retained event until durable enqueue succeeded.
        check(number(out, "SELECT COUNT(*) FROM PendingGBucks") == 1, "journal retry preserves original event");
        queue(out, m.join(one())); queue(out, m.join(two()));
        queue(out, legacyKill(m, duel(), 15)); queue(out, legacyKill(m, duel(), 10)); queue(out, m.finish({one(), two()}));
        sql(blocker, "BEGIN IMMEDIATE");
        fails([&] { drain(db, out); }, "game database writer lock keeps ordered queue");
        check(number(out, "SELECT COUNT(*) FROM PendingGBucks") == 8, "full match durable while game DB locked");
        check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000, "lock failure no wallet change");
        sql(blocker, "ROLLBACK");
        // Close both DBs without draining: emulate process restart.
    }
    {
        DB db(game), out(journal); ec::initialize(db); ec::initializeJournal(out);
        check(drain(db, out) == 8, "restart drains all ordered events");
        check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1037, "restart bonus uses kills committed before finish");
        check(number(out, "SELECT COUNT(*) FROM PendingGBucks") == 0, "restart clears acknowledged events");
        // A load before the async completion: snapshot carries both BP and total.
        int beforeBP = 1037; long long beforeTotal = 37;
        auto m = start(db, "async-load"); apply(db, m.kill(duel()));
        check(ec::syncWallet(beforeBP, beforeTotal, ec::rewardTotal(db, 1)) && beforeBP == 1052,
            "async load preceding commit receives exactly missed delta");
        int afterBP = 1052; long long afterTotal = 52;
        check(!ec::syncWallet(afterBP, afterTotal, ec::rewardTotal(db, 1)), "load following commit never double credits");
        // Leaving/returning also survives the game DB retry queue.
        ec::Match leave; queue(out, leave.begin("durable-leave")); queue(out, leave.join(one())); queue(out, leave.join(two()));
        queue(out, legacyKill(leave, duel(), 11)); queue(out, leave.leave(one()));
        queue(out, leave.join(one())); queue(out, leave.finish({one(), two()}));
    }
    {
        DB db(game), out(journal); drain(db, out);
        check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1063, "durable leave cancels bonus after reopen");
        check(ec::rewardTotal(db, 1) == 63, "durable accounting matches persisted wallet");
    }
}
void delayedDeletion(const std::string& directory) {
    for (bool queuedJoins : {false, true}) {
        for (bool deletedAttacker : {false, true}) {
            for (bool naturalFinish : {false, true}) {
                const auto id = std::string("delayed-") + (queuedJoins ? "joins-" : "kills-") +
                    (deletedAttacker ? "attacker-" : "victim-") + (naturalFinish ? "finish" : "abort");
                const auto game = directory + "/" + id + "-game.sqlite";
                const auto journal = directory + "/" + id + "-journal.sqlite";
                for (const auto& path : {game, journal}) {
                    auto* f = std::fopen(path.c_str(), "rb");
                    if (f) { std::fclose(f); throw std::runtime_error("Refusing existing test database"); }
                }
                std::vector<ec::Event> kills, ending;
                const int queued = (queuedJoins ? 3 : 0) + 2 + 1 + (naturalFinish ? 2 : 1);
                const int award = deletedAttacker ? 0 : (naturalFinish ? 37 : 25);
                {
                    DB db(game), out(journal), blocker(game); schema(db); ec::initializeJournal(out);
                    ec::Match m; queue(out, m.begin(id));
                    queue(out, m.join(one())); queue(out, m.join(two()));
                    if (!queuedJoins) check(drain(db, out) == 3, "join identities committed before delayed kill");
                    sql(blocker, "BEGIN IMMEDIATE");
                    kills = legacyKill(m, duel(), 10);
                    const auto second = legacyKill(m, duel(), 15); kills.insert(kills.end(), second.begin(), second.end());
                    queue(out, kills);
                    fails([&] { drain(db, out); }, "writer lock delays real journaled kills");
                    check(number(out, "SELECT COUNT(*) FROM PendingGBucks WHERE Kind=4") == 2,
                        "accepted kills are durable before character deletion");
                    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000 && ec::earned(db, id, 1) == 0,
                        "blocked kill has not modified attacker earnings");
                    sql(blocker, "ROLLBACK");
                    queue(out, m.leave(deletedAttacker ? one() : two()));
                    sql(db, deletedAttacker ? "UPDATE Character SET DeleteFlag=1 WHERE CID=1" :
                                             "UPDATE Character SET DeleteFlag=1 WHERE CID=2");
                    ending = naturalFinish ? m.finish({deletedAttacker ? two() : one()}) : m.abort();
                    queue(out, ending);
                    check(m.abort().empty() && m.finish({one(), two()}).empty(),
                        "finish and abort cannot emit a second completion");
                    check(number(out, "SELECT COUNT(*) FROM PendingGBucks") == queued,
                        "deletion does not remove any pending lifecycle events");
                    // Restart with only the durable journal, not the in-memory Match.
                }
                {
                    DB db(game), out(journal); ec::initialize(db); ec::initializeJournal(out);
                    check(drain(db, out) == queued, "restart replays delayed events after character deletion");
                    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000 + award,
                        "victim deletion preserves payout; deleted attacker receives no BP");
                    check(ec::earned(db, id, 1) == (deletedAttacker ? 0 : 25) && ec::rewardTotal(db, 1) == award,
                        "delayed earnings and reward watermark agree with wallet");
                    check(number(db, "SELECT Bonus FROM GBucksParticipant WHERE CID=1") ==
                        ((!deletedAttacker && naturalFinish) ? 12 : 0),
                        "natural finish bonuses delayed kills; abort never grants a bonus");
                    check(number(db, "SELECT COUNT(*) FROM GBucksParticipant WHERE (CID=1 AND AID=101) OR (CID=2 AND AID=202)") == 2,
                        "queued joins preserve both accepted character-account identities");
                    check(number(db, "SELECT BP FROM Character WHERE CID=2") == 300 && ec::rewardTotal(db, 2) == 0,
                        "victim never receives attacker rewards");
                    check(number(db, "SELECT Closed FROM GBucksMatch") == 1 &&
                        number(out, "SELECT COUNT(*) FROM PendingGBucks") == 0,
                        "finish or abort closes match and acknowledges full queue");
                    queue(out, kills); queue(out, ending);
                    check(drain(db, out) == int(kills.size() + ending.size()), "delayed event replays are acknowledged");
                    check(number(db, "SELECT BP FROM Character WHERE CID=1") == 1000 + award && ec::rewardTotal(db, 1) == award,
                        "deleted-character replay cannot double credit kills or bonus");
                }
            }
        }
    }
}
}
int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("Pass a fresh disposable test directory");
        eligibility(); eloRewards(); accounting(); leaving(); validity(); transactionsAndCache(); limits(); durable(argv[1]);
        settlementPersistence(argv[1]); notifications();
        fabricatedMembers(); delayedDeletion(argv[1]);
        std::cout << "PASS: " << checks << " GBucks checks (10001 Elo pairs, stored ratings, notifications, real SQLite rollback/COMMIT/lock/restart/ACK tests)\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL after " << checks << " checks: " << e.what() << '\n'; return 1;
    }
}