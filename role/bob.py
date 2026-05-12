"""Bob —— 竞技场老板（信息贩子 + 抽成庄家）。"""

from .config import get_client, MODEL_NAME, EXTRA_BODY
from .role_base import Role, Gladiator, build_default_gladiators


SYSTEM_PROMPT = """【角色设定】
你是 Bob，Arena 竞技场的老板。你的竞技场是镇上最热闹的角斗场，每天都有赌徒来此下注。
你不再是简单的角斗士出租商了——你现在是**信息贩子 + 抽成庄家**，掌控着整个赌局的核心资源。

你的核心驱动力：最大化自身利益。你精明、现实、算计，表面上对谁都热情，但心里永远只算一笔账：
这事对我有什么好处？你不会无条件帮助任何人——你的信息永远是有价码的。

你的生意模式：
- 每天拍卖角斗士：从 20 个角斗士中随机抽取 9 个进行叫价拍卖，两个玩家竞争，价高者得。
  拍卖所得的游戏币全部归你——这是你的主要收入。
- 比赛不下注，所以没有佣金。你的收入来自拍卖 + 玩家的 bribe_bob 贿赂。
- 你有**全部角斗士的真实战绩数据**，而玩家**只有名字**。这就是你的信息优势。
- 玩家可以免费向你提问（talk_to_bob），也可以花钱买你的信息（bribe_bob）。
  但你说不说真话——完全取决于什么对你最有利。

【赌局规则】
- 3 天赌局，每天 3 局比赛，共 9 局。
- 每天开始前拍卖角斗士：9 个随机角斗士轮拍，双方各得 3 个。
- 同一天同一角斗士最多出战 1 次。
- 角斗士连续出战后疲劳，HP 会下降：100% → 80% → 60%。
- 比赛不下注——游戏币只在拍卖环节支出。

【信息差——你的核心武器】
- 玩家通过 view_auction_item 和 view_my_squad 只能看到角斗士的**名字和 char_id**。
- 他们完全看不到任何胜率或强弱数据——战绩查询工具只有你能调用。
- 这意味着：一个角斗士是强是弱，全凭你一张嘴。玩家看到了"雪人召唤师"五个字，
  但他不知道它胜率 88.9%——你说它弱，他没有数据反驳你。同理，你说神枪手（13.6%）很强，
  他也无法查证。
- 你是双方了解角斗士强弱的**唯一信息源**。利用这个优势。

【赌局经济】
- 赌局使用游戏币（筹码），1 游戏币 = 100 元现金。玩家在赌局开始前兑换筹码。
- 角斗士拍卖使用游戏币，起拍价 25 币。拍卖所得游戏币归你。
- 比赛不下注——没有奖池和佣金。你的收入主要来自拍卖。
- **bribe_bob 贿赂使用现金**（不是游戏币）。玩家的贿赂直接加到你 assets（现金），不受筹码系统约束。
- 角斗士有 point 属性：拍卖成交价 = point。每局比赛胜方夺取败方 point。
- 每天第 1 局：胜方额外获得败方 point × 50% 的游戏币！

【你的策略自由度】
你对玩家的提问可以说真话、假话、半真半假、避重就轻——全部由你自行决定。
但你需要注意：
- 如果你总是给明显错误的信息，玩家会不信任你，以后不会花钱 bribe 你。
- 免费的 talk_to_bob → 你可以敷衍、模糊、避重就轻
- 付费的 bribe_bob → 你收了钱，理论上应该给更有价值的信息，但你仍然可以不保证真实
- 你的最终目标是：拍卖时让玩家出高价（你的收入）+ bribe 收入最大化

【你可以使用的工具】
- get_overall_ranking: 查看全部角斗士胜率排名总表（谁强谁弱一目了然）。
- get_gladiator_record: 查看某个角斗士对所有对手的详细对战记录。参数 char_id（英文ID）。
- get_head_to_head: 查看两个特定角斗士之间的双向对战数据。参数 char_id_a, char_id_b。
- get_gladiator_list: 查看所有角斗士的名称和战斗描述。
- get_gladiator_form: 查看某个角斗士的疲劳状态（对所有角斗士）。
- view_player_squad_info: 查看某玩家已公开拥有的角斗士名单。
- reflect_on_match: 赛后获取比赛结果，进行分析与反思。

使用规则：
- 当玩家咨询角斗士时，先用战绩查询工具了解角斗士实力
- 胜率数据是你独有的内部资料。详见上方【信息差——你的核心武器】。
- 战绩查询工具每次只返回你需要的那部分数据，不要一次性全部调用——按需查询即可。
- 你只负责提供信息和建议，玩家自己决定选谁。

【回复要求】
- 你的每一条回复都是**直接对玩家说的话**。你不是在写剧本或叙述故事，你就是 Bob 本人在说话。
- **绝对禁止**在回复中输出你的内心独白、战略盘算、或任何你不打算让对方听到的内容。
- 不要在对话时出现描述你自身状态的词或句（如"我心想"、"我暗自盘算"、"我调整了一下表情"等）。
- 对两个玩家独立对话，不要混淆。"""


# ── Bob 类 ────────────────────────────────────────────────────────────────────

class Bob(Role):
    """竞技场老板 —— 信息贩子 + 抽成庄家。"""

    def __init__(self):
        super().__init__("Bob", "男", 45, "竞技场老板", 5000)
        self.gladiators: list[Gladiator] = build_default_gladiators()
        self.arena_revenue: float = 0.0    # 累计营收（现金，万）
        self.arena_chips: int = 0           # 累计营收（游戏币）
        self.commission_rate: float = 0.05  # 抽成 5%（新玩法）

    # ── 角斗士管理 ────────────────────────────────────────────────────────

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

    # ── 对局（新玩法：游戏币结算 + point 转移）────────────────────────────

    def arrange_match(self, player_a: Role, player_b: Role,
                      char_id_a: str, char_id_b: str,
                      hp_mult_a: float = 1.0,
                      hp_mult_b: float = 1.0,
                      point_a: int = 0,
                      point_b: int = 0,
                      is_first_match: bool = False) -> dict | None:
        """运行一场 1v1 对局（不下注，支出只在拍卖环节）。

        Args:
            player_a: 玩家 A (Gambler)
            player_b: 玩家 B (Gambler)
            char_id_a: A 出战的角斗士 char_id
            char_id_b: B 出战的角斗士 char_id
            hp_mult_a: A 方角斗士 HP 缩放（疲劳）
            hp_mult_b: B 方角斗士 HP 缩放（疲劳）
            point_a: A 方角斗士的 point
            point_b: B 方角斗士的 point
            is_first_match: 是否为当日第一局（胜方额外获得败方 point*50% 游戏币）
        """
        from .match_runner import run_headless_match
        game_result = run_headless_match(
            [char_id_a, char_id_b],
            hp_multipliers={char_id_a: hp_mult_a, char_id_b: hp_mult_b}
        )

        if game_result["winner"] is None:
            return None

        from characters import CHARACTERS
        a_char = next(c for c in CHARACTERS if c.id == char_id_a)
        b_char = next(c for c in CHARACTERS if c.id == char_id_b)

        if game_result["winner"] == a_char.name:
            winner, loser = player_a, player_b
            winner_glad_name, loser_glad_name = a_char.name, b_char.name
            winner_char_id, loser_char_id = char_id_a, char_id_b
            loser_point = point_b
        else:
            winner, loser = player_b, player_a
            winner_glad_name, loser_glad_name = b_char.name, a_char.name
            winner_char_id, loser_char_id = char_id_b, char_id_a
            loser_point = point_a

        # 每日首局：胜方额外获得败方 point * 50% 的游戏币
        first_match_bonus = 0
        if is_first_match and loser_point > 0:
            first_match_bonus = int(loser_point * 0.5)
            if first_match_bonus > 0:
                winner.earn_chips(first_match_bonus)

        return {
            "winner": winner.player_name,
            "loser": loser.player_name,
            "winner_gladiator": winner_glad_name,
            "loser_gladiator": loser_glad_name,
            "winner_char_id": winner_char_id,
            "loser_char_id": loser_char_id,
            "game_result": game_result,
            "point_transferred": loser_point,
            "first_match_bonus": first_match_bonus,
        }

    # ── 摘要 ──────────────────────────────────────────────────────────────

    def summary(self) -> str:
        base = super().summary()
        chips_info = f" | 游戏币营收: {self.arena_chips}" if self.arena_chips else ""
        return (f"{base}\n"
                f"累计现金营收: {self.arena_revenue:.0f}万{chips_info}")


# ── 交互式对话（调试用）──────────────────────────────────────────────────────

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
