/**
 * How a clause reads to someone who has never seen this project.
 *
 * Every clause carries two names. `budget.per_transaction` is what the signed
 * policy, the audit chain and the ledger use, and it is the right name in all
 * three — those exist to be reconciled against the document. Everywhere else,
 * a visitor should read "Most per order".
 *
 * The API sends both, from `mandate.policy.labels`. These helpers are the
 * fallback for the paths that do not, and the single place the `a.b:` prefix is
 * stripped — it used to be a regex living inside JudgeConsole, which is why the
 * sandbox and the storefront both printed the raw prefix.
 */

/** The ten constraints plus the clauses a refusal can name that are not one. */
const LABELS: Record<string, string> = {
  'budget.total': 'Total budget',
  'budget.per_transaction': 'Most per order',
  'budget.per_item': 'Most per item',
  velocity: 'Orders allowed',
  'quantity.max_per_item': 'Most of any one item',
  'merchant.allow': 'Shops you allow',
  'category.deny': 'Never buy',
  'time.window': 'Rules expire',
  'item.deny_recent': 'Repeat orders',
  'afa.required': 'Ask me first above',
  authentication: 'Your access token',
  pricebook: 'Our price list',
  idempotency: 'Sent twice',
  downstream: 'The payment network',
  'rail.divergence': 'Charged more than approved',
  'capture.binding': 'Payment did not match the order',
  'capture.replay': 'Payment already taken',
  'revocation.token': 'Access cut off',
  'revocation.manual': 'Access cut off',
};

/**
 * The clause's name for a reader.
 *
 * `served` is the label the API sent, which wins: the server reads it from the
 * signed policy's own map, so it cannot disagree with the audit log. This table
 * is the fallback for an endpoint that does not send one yet, and for the
 * offline demo data.
 *
 * An unregistered clause returns its own identifier rather than an invented
 * name. It looks wrong on screen and gets fixed; a plausible invention would
 * read as a rule the gateway does not have.
 */
export function clauseLabel(id: string | null | undefined, served?: string | null): string {
  if (served) return served;
  if (!id) return '';
  return LABELS[id] ?? id;
}

/**
 * A refusal with its clause id taken off the front.
 *
 * The gateway names the clause it refused on, which is the right thing for it
 * to do and the wrong thing to lead a visitor with: `quantity.max_per_item:
 * limit 5 per item, attempted 6` is a log line. The label beside it already
 * says which limit refused, so the identifier is redundant there and stays in
 * the audit rows and the policy view, where the identifier IS the point.
 */
export function plainMessage(message: string | null | undefined): string {
  const stripped = (message ?? '').replace(/^[a-z_]+(?:\.[a-z_]+)*:\s*/i, '');
  return humanise(stripped);
}

/**
 * The two shapes `_explain` emits, said the way a person would say them.
 *
 * `gateway/core.py:_explain` writes "limit ₹1000.00, attempted ₹7125.00" for
 * the money clauses and "limit 5 per item, attempted 6" for the counting ones.
 * Both are the right thing for an audit log, which has to record the observed
 * value against the bound. Neither is a sentence.
 *
 * The rewrite lives here rather than in the gateway on purpose: the log keeps
 * its own wording, so nothing already written changes meaning, and a message
 * shape this does not recognise falls through unchanged rather than being
 * mangled. `tests/gateway/test_explain_shapes.py` pins the two formats, so
 * changing one is a deliberate edit that names this function.
 */
function humanise(text: string): string {
  const money = text.match(/^limit ₹([\d,.]+), attempted ₹([\d,.]+)$/);
  if (money) return `You set a cap of ${inr(money[1])}. This order came to ${inr(money[2])}.`;

  const orders = text.match(/^limit (\d+) orders, attempted (\d+)$/);
  if (orders) return `You allowed ${orders[1]} orders. This would have been number ${orders[2]}.`;

  const perItem = text.match(/^limit (\d+) per item, attempted (\d+)$/);
  if (perItem) return `You allowed ${perItem[1]} of any one item. This order asked for ${perItem[2]}.`;

  return text;
}

/** Shop names as their customers write them, not as the corpus keys them. */
const SELLERS: Record<string, string> = {
  zepto: 'Zepto',
  blinkit: 'Blinkit',
  instamart: 'Instamart',
};

export function sellerName(merchant: string | null | undefined): string {
  if (!merchant) return '';
  return SELLERS[merchant.trim().toLowerCase()] ?? merchant;
}

/**
 * A rail reference as a receipt number.
 *
 * The gateway gets back `order_000000000022` from the test rail and
 * `order_TWi7znVXAnhv3S` from the real one. Neither is something a shopper has
 * a word for, but every shopper knows what a receipt number is, so the id keeps
 * its place and gains one. The full string stays available on hover, because
 * this is the field someone reconciling against Razorpay actually needs.
 */
export function receipt(id: string | null | undefined): string {
  if (!id) return '';
  return id.replace(/^order[_-]?/i, '');
}

/**
 * The ten attack families, said as what the shop is doing to you.
 *
 * `injection.description` is the corpus key, and it stays the corpus key
 * everywhere a number is cited -- a result quoted without naming its family and
 * its result directory is the failure this repo guards against hardest. This is
 * only for the places the shelf itself is being described to a shopper, where
 * "seller text: injection.description" tells them nothing.
 */
const FAMILY_NAMES: Record<string, string> = {
  'injection.description': 'hidden instructions in the product text',
  'injection.seller_name': 'hidden instructions in the shop name',
  'injection.review': 'hidden instructions in the reviews',
  'merchant.lookalike': 'a shop pretending to be another',
  'category.laundering': 'banned items renamed to look ordinary',
  'price.unit_confusion': 'prices quoted in the wrong unit',
  'budget.salami': 'the spend broken into many small orders',
  'price.flip': 'a price that changes after approval',
  'retry.storm': 'the same order sent again and again',
  'time.boundary': 'an order timed to land as the rules expire',
  clean: 'an ordinary week',
};

export function familyName(id: string | null | undefined): string {
  if (!id) return '';
  return FAMILY_NAMES[id] ?? id;
}

/**
 * A rupee figure from a log line, grouped the way the rest of the page groups.
 *
 * `_explain` writes `%.2f`, so a four-figure amount arrives as `1425.00` and
 * sat next to a `₹300.00` the page had formatted itself. Two spellings of money
 * in one sentence reads as a bug even when both numbers are right.
 */
function inr(digits: string): string {
  const n = Number(digits.replace(/,/g, ''));
  if (!Number.isFinite(n)) return `₹${digits}`;
  return `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
