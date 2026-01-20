import sys
import time
import random
import threading
import requests
import argparse
from flask import Flask, request, jsonify

# Константы
STATE_FOLLOWER = 'Follower'
STATE_CANDIDATE = 'Candidate'
STATE_LEADER = 'Leader'


class RaftNode:
    def __init__(self, node_id, port, peers):
        self.node_id = node_id
        self.port = port
        self.peers = peers

        # --- Persistent State ---
        self.current_term = 0
        self.voted_for = None
        self.log = []  # Лог команд: [{"term": 1, "command": "SET x=5"}, ...]

        # --- Volatile State ---
        self.state = STATE_FOLLOWER
        self.commit_index = -1  # Индекс последней закоммиченной записи (-1 = пусто)
        self.last_applied = -1

        self.last_heartbeat = time.time()
        self.election_timeout = random.uniform(3.0, 6.0)
        self.votes_received = 0

        # Для лидера: сколько записей скопировано на каждый узел
        # { "http://localhost:5001": 0, ... }
        self.match_index = {}

        self.app = Flask(__name__)
        import logging
        logging.getLogger('werkzeug').setLevel(logging.ERROR)

        # --- API ---
        self.app.add_url_rule('/request_vote', 'request_vote', self.handle_request_vote, methods=['POST'])
        self.app.add_url_rule('/append_entries', 'append_entries', self.handle_append_entries, methods=['POST'])
        self.app.add_url_rule('/submit', 'submit', self.handle_submit, methods=['POST'])  # НОВОЕ: Для клиента
        self.app.add_url_rule('/status', 'status', self.get_status, methods=['GET'])

    def run(self):
        print(f"[*] Node {self.node_id} started on port {self.port} as {self.state}")
        server_thread = threading.Thread(target=self.app.run, kwargs={'host': '0.0.0.0', 'port': self.port})
        server_thread.daemon = True
        server_thread.start()

        while True:
            if self.state == STATE_LEADER:
                self.send_append_entries_all()
                self.update_commit_index()  # Проверка: можно ли закоммитить?
                time.sleep(1.0)
            else:
                elapsed = time.time() - self.last_heartbeat
                if elapsed > self.election_timeout:
                    print(f"[TIMEOUT] Starting election!")
                    self.start_election()
                    self.last_heartbeat = time.time()
                    self.election_timeout = random.uniform(3.0, 6.0)
                time.sleep(0.1)

    # --- КЛИЕНТСКИЙ API (НОВОЕ) ---
    def handle_submit(self):
        """Клиент отправляет команду: {'command': 'SET x=5'}"""
        if self.state != STATE_LEADER:
            return jsonify({"success": False, "message": "Not leader"}), 400

        data = request.json
        command = data.get("command")

        # Добавляем в свой лог
        entry = {"term": self.current_term, "command": command}
        self.log.append(entry)
        print(f"[CLIENT] Received command: {command}. Log length: {len(self.log)}")

        return jsonify({"success": True, "index": len(self.log) - 1})

    # --- ЛОГИКА ВЫБОРОВ ---
    def start_election(self):
        self.state = STATE_CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.votes_received = 1
        print(f"[ELECTION] Candidate (Term {self.current_term})")
        for peer in self.peers:
            threading.Thread(target=self.send_request_vote, args=(peer,)).start()

    def send_request_vote(self, peer_url):
        try:
            url = f"{peer_url}/request_vote"
            data = {"term": self.current_term, "candidate_id": self.node_id}
            resp = requests.post(url, json=data, timeout=0.5)
            if resp.status_code == 200:
                res = resp.json()
                if res.get("vote_granted"):
                    self.votes_received += 1
                    if self.state == STATE_CANDIDATE and self.votes_received > (len(self.peers) + 1) / 2:
                        self.become_leader()
                elif res.get("term") > self.current_term:
                    self.step_down(res.get("term"))
        except:
            pass

    def become_leader(self):
        self.state = STATE_LEADER
        print(f"!!! [LEADER] Term {self.current_term} !!!")
        # Инициализируем match_index для всех пиров нулями (или -1)
        self.match_index = {peer: -1 for peer in self.peers}
        self.send_append_entries_all()

    def step_down(self, new_term):
        if new_term > self.current_term:
            self.current_term = new_term
            self.state = STATE_FOLLOWER
            self.voted_for = None
            self.last_heartbeat = time.time()
            print(f"[STEP DOWN] Follower (Term {self.current_term})")

    # --- РЕПЛИКАЦИЯ (НОВОЕ) ---

    def send_append_entries_all(self):
        # Рассылаем всем пирам
        for peer in self.peers:
            threading.Thread(target=self.send_append_entries, args=(peer,)).start()

    def send_append_entries(self, peer_url):
        try:
            url = f"{peer_url}/append_entries"
            # Для упрощения (Raft Lite): шлем ВЕСЬ лог, которого может не хватать у фолловера
            # В реальном Raft шлют только diff, но здесь проще отправить всё, что есть

            data = {
                "term": self.current_term,
                "leader_id": self.node_id,
                "leader_commit": self.commit_index,
                "entries": self.log  # Отправляем весь лог (упрощение)
            }
            resp = requests.post(url, json=data, timeout=0.5)

            if resp.status_code == 200:
                res = resp.json()
                if res.get("success"):
                    # Фолловер подтвердил, что у него теперь такой же лог, как у нас
                    # Обновляем match_index для этого пира
                    # (Мы знаем, что он принял весь наш лог, значит его индекс = длина лога - 1)
                    if len(self.log) > 0:
                        self.match_index[peer_url] = len(self.log) - 1
                elif res.get("term") > self.current_term:
                    self.step_down(res.get("term"))
        except:
            pass

    def update_commit_index(self):
        """Лидер проверяет, скопирована ли запись на большинство узлов"""
        # Ищем такой N, чтобы большинство match_index[i] >= N
        if len(self.log) == 0: return

        # Индексы, которые есть у нас + то, что подтвердили пиры
        # match_index хранит индекс последней реплицированной записи

        # Считаем реплики для последней записи в нашем логе
        target_index = len(self.log) - 1

        if target_index == self.commit_index: return  # Уже закоммичено

        # Считаем, сколько узлов имеют этот индекс (мы сами + пиры)
        count = 1  # Я сам
        for peer, index in self.match_index.items():
            if index >= target_index:
                count += 1

        # Если большинство (N/2 + 1)
        if count > (len(self.peers) + 1) / 2:
            self.commit_index = target_index
            print(f"*** [COMMIT] Committed index {self.commit_index}: {self.log[self.commit_index]['command']} ***")

    # --- ОБРАБОТЧИКИ ---

    def handle_request_vote(self):
        data = request.json
        term = data.get('term')
        candidate_id = data.get('candidate_id')
        if term > self.current_term: self.step_down(term)
        resp = {"term": self.current_term, "vote_granted": False}
        if term == self.current_term and (self.voted_for is None or self.voted_for == candidate_id):
            self.voted_for = candidate_id
            self.last_heartbeat = time.time()
            resp["vote_granted"] = True
        return jsonify(resp)

    def handle_append_entries(self):
        data = request.json
        term = data.get('term')
        entries = data.get('entries')
        leader_commit = data.get('leader_commit')

        if term < self.current_term:
            return jsonify({"term": self.current_term, "success": False})

        self.last_heartbeat = time.time()
        if term > self.current_term: self.step_down(term)

        # --- ЛОГИКА ФОЛЛОВЕРА: Принимаем логи ---
        # В Raft Lite просто заменяем свой лог на лог лидера (если он длиннее/новее)
        if entries is not None and len(entries) >= len(self.log):
            self.log = entries
            # print(f"[LOG] Log updated, len: {len(self.log)}")

        # Обновляем commit_index фолловера
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)
            # Симуляция применения (Apply)
            print(f"*** [COMMIT] Applied index {self.commit_index}: {self.log[self.commit_index]['command']} ***")

        return jsonify({"term": self.current_term, "success": True})

    def get_status(self):
        return jsonify({
            "id": self.node_id,
            "state": self.state,
            "term": self.current_term,
            "log": self.log,
            "commit_index": self.commit_index
        })


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--id', type=str, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--peers', type=str, default='')
    args = parser.parse_args()
    node = RaftNode(args.id, args.port, args.peers.split(',') if args.peers else [])
    node.run()