\# Hunter2



Hunter2 is a clean rebuild of the original `hunter1` Telegram Mini App project.



The goal is to combine the working parts of the previous project into one organized codebase with a clear separation between:



\- backend API

\- frontend Mini App

\- Telegram bot

\- scheduled jobs

\- shared database



\## Main features



Hunter2 is intended to support:



\- DCA calculator

\- asset comparison

\- DCA vs lump sum

\- stocks, ETFs, crypto, and commodities

\- Market Temperature / Opportunity Scanner

\- long-term RSI and Stochastic RSI

\- 200-week SMA analysis

\- drawdown analysis

\- trend classification

\- opportunity and overheat scores

\- favorites

\- alert preferences

\- Telegram transition alerts

\- scheduled market refreshes



\## Planned architecture



```text

Frontend Mini App

&#x20;       |

&#x20;       v

FastAPI Backend

&#x20;       |

&#x20;       v

PostgreSQL Database

&#x20;       ^

&#x20;       |

Scheduled Refresh

&#x20;       |

&#x20;       v

Telegram Alerts



hunter2/

├── backend/

├── frontend/

├── bot/

├── scripts/

├── .gitignore

└── README.md

