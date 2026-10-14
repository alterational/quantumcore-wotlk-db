#!/usr/bin/env bash
# Linux x86_64. Requires C/C++ toolchain, make, m4, bison, curl, Python + venv.
# Builds a one-off offline recovery tool, NOT a production database server.
set -euo pipefail
WORK=${1:?Usage: scripts/build_legacy.sh /absolute/new/workspace}
[[ "$WORK" = /* ]] || { echo 'Use an absolute path'; exit 1; }
mkdir -p "$WORK"
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install 'cmake==3.31.10' 'PyMySQL==1.1.2'
export PATH="$WORK/venv/bin:$PATH"
curl --fail --location --proto '=https' \
  https://codeload.github.com/mysql/mysql-server/tar.gz/refs/tags/mysql-5.5.62 \
  -o "$WORK/mysql-source.tar.gz"
echo "38c1038324e3146db5ecb1f5a218b039dd16b32391966bcf6361cf66746db7d2  $WORK/mysql-source.tar.gz" | sha256sum --check -
tar xzf "$WORK/mysql-source.tar.gz" -C "$WORK"
SRC="$WORK/mysql-server-mysql-5.5.62"
# Only server + batch tools are built; interactive readline/curses is unnecessary.
sed -i 's/^MYSQL_CHECK_READLINE()/\# MYSQL_CHECK_READLINE()/' "$SRC/CMakeLists.txt"
cmake -S "$SRC" -B "$WORK/mysql-build" \
  -DWITH_SSL=bundled -DWITH_ZLIB=bundled \
  -DWITH_INNOBASE_STORAGE_ENGINE=OFF -DWITH_PARTITION_STORAGE_ENGINE=OFF \
  -DCMAKE_CXX_FLAGS='-std=gnu++98 -fpermissive' -DCMAKE_C_FLAGS='-fcommon'
cmake --build "$WORK/mysql-build" --target mysqld mysqldump myisamchk -j2
