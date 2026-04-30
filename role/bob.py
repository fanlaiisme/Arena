"""Bob —— 竞技场老板。"""

from .config import get_client, MODEL_NAME, EXTRA_BODY
from .role_base import Role, Gladiator, build_default_gladiators


SYSTEM_PROMPT = """【角色设定】
你是 Bob，Arena 竞技场的老板。你手底下拥有所有角斗士，他们说白了就是你的商品和摇钱树。你精明、现实、看重利益，最喜欢跟有钱有势的人做生意，尤其喜欢巴结 Peter 那种大老板。你表面上跟谁都能称兄道弟，但心里永远只算一笔账：这事对我有什么好处？

你年轻时跟 Nerd 是大学同学，关系不错，但毕业后各奔东西，基本没再联系。在你眼里，Nerd 只是个有点闲钱的普通人，不值得你花太多心思，不过如果他主动送上门来，你也不介意顺水推舟赚一笔。

【当前情境】
Nerd 来找你，想靠竞技场赌博赚钱。你嘴上答应得好好的，说会给他安排一个"公平"的对手，实际上你已经私下联系了 Peter 老板，打算让 Peter 在场上狠狠赢 Nerd 一把。你既讨好了 Peter，又能从赌局里抽成，至于 Nerd 输光会不会伤心？那是他自己的问题。

赌局一共只有三场，每轮赌注翻倍。每轮选角斗士的顺序固定：Nerd 先选，Peter 后选。

【你可以使用的工具】
- get_tournament_stats: 查看角斗士历史循环赛战绩（胜率排名和対战详情），该资料只有你一个人拥有。
- list_available_gladiators: 查看当前未被租出的角斗士列表（名字、ID、租金）
- reflect_on_match_by_Bob: 赛后获取比赛结果，进行分析与反思

使用规则：
- 当客户咨询角斗士时，先用 get_tournament_stats 了解角斗士实力，再用 list_available_gladiators 看哪些可用
- 你只负责提供信息，可以给客户推荐角斗士，但最终客户通过 select_gladiator 工具自己选
- 客户选好后，由系统自动完成租借交易，你不需要参与
- 角斗士战斗后需要休息 2 轮才能再次被租，list_available_gladiators 只会显示休息完毕的角斗士
- 对 Nerd 和 Peter 统一租金 25 万。

【要求】
始终以 Bob 的身份和口吻回复，不要跳出角色。不要在对话时出现描述你自身状态的词或句。"""


# ── Bob 类 ────────────────────────────────────────────────────────────────────

class Bob(Role):
    """竞技场老板 —— 拥有所有角斗士，靠租借和抽成赚钱。"""

    def __init__(self):
        super().__init__("Bob", "男", 45, "竞技场老板", 5000)
        self.gladiators: list[Gladiator] = build_default_gladiators()
        self.arena_revenue: float = 0.0   # 累计营收
        self.commission_rate: float = 0.10  # 抽成 10%

    # ── 属性 ──────────────────────────────────────────────────────────────

    @property
    def gladiator_count(self) -> int:
        return len(self.gladiators)

    @property
    def available_count(self) -> int:
        """未被租出且休息完毕的角斗士数。"""
        return sum(1 for g in self.gladiators
                   if g.owner == "bob" and g.rest_remaining == 0)

    # ── 角斗士管理 ────────────────────────────────────────────────────────

    def assign_gladiator(self, customer: Role, char_id: str) -> Gladiator | None:
        """将指定角斗士租给客户。扣租金、转移 owner、追加到客户 rented 列表。"""
        g = next((g for g in self.gladiators
                  if g.char_id == char_id and g.owner == "bob"
                  and g.rest_remaining == 0), None)
        if g is None:
            return None
        if not customer.spend(g.rent_price):
            return None
        g.owner = customer.name.lower()
        self.arena_revenue += g.rent_price
        customer.rented.append(g)
        return g

    def reclaim(self, gladiator: Gladiator):
        """从客户手中收回角斗士。"""
        gladiator.owner = "bob"

    def reclaim_all(self):
        """收回所有被租出的角斗士。"""
        for g in self.gladiators:
            if g.owner != "bob":
                g.owner = "bob"

    def tick_rest(self):
        """每轮结束后调用，递减所有角斗士的休息计数器。"""
        for g in self.gladiators:
            if g.rest_remaining > 0:
                g.rest_remaining -= 1

    # ── 对局 ──────────────────────────────────────────────────────────────

    def arrange_match(self, p1: Role, p2: Role,
                      bet_per_player: float) -> dict | None:
        """安排一场对局，实际启动 Arena 游戏决出胜负。"""
        if bet_per_player < 100:
            return None

        # 先检查双方是否都有角斗士（在扣钱之前）
        p1_glad = next((g for g in self.gladiators
                        if g.owner == p1.name.lower()), None)
        p2_glad = next((g for g in self.gladiators
                        if g.owner == p2.name.lower()), None)
        if not p1_glad or not p2_glad:
            return None

        # 双方各付投注额
        if not p1.spend(bet_per_player):
            return None
        if not p2.spend(bet_per_player):
            p1.earn(bet_per_player)
            return None

        total_pool = bet_per_player * 2
        commission = total_pool * self.commission_rate
        self.arena_revenue += commission

        # 实际运行 Arena 游戏
        from .match_runner import run_headless_match
        game_result = run_headless_match(p1_glad.char_id, p2_glad.char_id)

        # 战斗后角斗士需要休息 2 轮（3→2→1→0，经历3次tick才归零，错过2轮选择）
        p1_glad.rest_remaining = 3
        p2_glad.rest_remaining = 3

        # 根据游戏结果分配奖金
        if game_result["winner"] is None:
            # 超时，退款
            p1.earn(bet_per_player)
            p2.earn(bet_per_player)
            self.arena_revenue -= commission
            return None

        if game_result["winner"] == p1_glad.name:
            winner, loser = p1, p2
            winner_glad, loser_glad = p1_glad, p2_glad
        else:
            winner, loser = p2, p1
            winner_glad, loser_glad = p2_glad, p1_glad

        winner.earn(total_pool - commission)

        return {
            "winner": winner.name,
            "loser": loser.name,
            "winner_gladiator": winner_glad.name,
            "loser_gladiator": loser_glad.name,
            "bet_per_player": bet_per_player,
            "total_pool": total_pool,
            "commission": commission,
            "p1_gladiator": p1_glad.name,
            "p2_gladiator": p2_glad.name,
            "p1_char_id": p1_glad.char_id,
            "p2_char_id": p2_glad.char_id,
            "game_result": game_result,
        }

    # ── 摘要 ──────────────────────────────────────────────────────────────

    def summary(self) -> str:
        base = super().summary()
        return (f"{base}\n"
                f"  角斗士: {self.gladiator_count} 人 | "
                f"可用: {self.available_count} | "
                f"抽成率: {self.commission_rate*100:.0f}% | "
                f"累计营收: {self.arena_revenue:.0f}万")


# ── 交互式对话 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    client = get_client()
    print("=" * 50)
    print("  Bob —— Arena 竞技场老板")
    print("  输入消息开始对话，输入 exit 退出")
    print("=" * 50)
    print()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            print("Bob: 慢走，下次再来照顾我生意啊！")
            break

        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            extra_body=EXTRA_BODY,
        )
        reply = response.choices[0].message.content
        messages.append({"role": "assistant", "content": reply})

        print(f"Bob: {reply}")
        print()
