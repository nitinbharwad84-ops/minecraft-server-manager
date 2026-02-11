"""
eula_manager.py
===============
Comprehensive Minecraft End User License Agreement (EULA) management.

Handles EULA acceptance workflow with detailed result objects,
validation, interactive prompts, and full legal text display.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# The official EULA URL
EULA_URL = "https://www.minecraft.net/en-us/eula"

# Standard eula.txt template
EULA_TEMPLATE = """\
#By changing the setting below to TRUE you are indicating your agreement to our EULA ({url}).
#{timestamp}
eula={value}
"""

# Full Minecraft EULA text for display
MINECRAFT_EULA_TEXT = """
MINECRAFT END USER LICENSE AGREEMENT

This End User License Agreement ("Agreement") is between you and us (Mojang AB and Microsoft Corporation,
or if applicable, one of its local affiliates). You should read the whole thing (and the Privacy Policy
and Brand and Asset Usage Guidelines), but here's the basic idea:

RULES FOR OUR SERVICE AND SOFTWARE

By using our Game, you accept and agree to be bound by this Agreement and our Privacy Policy.

If you do not agree to this Agreement, do not use our Game.

This Agreement is a legal document that explains what you can and can't do with the Game. The Game means:
- Minecraft and Minecraft: Java Edition
- Minecraft Realms and all related software, updates, data, and services associated with it

The Game is our software, so you may not:
- distribute any modification of the Game, or make it available to others
- make commercial use of anything we've made
- try to make money from anything we've made
- let others access our content in an unfair or unreasonable way

ONE MAJOR RULE:

You may not distribute anything we've made, or allow others to use it in a way that is unfair or unreasonable.
But we want you to be able to have fun with the Game, so we're not trying to prevent you from playing with
modifications or distributing your creations - you can still do that subject to the other Rules in this Agreement.

If you've bought the Game:
- You own the media on which it came, but we or our licensors own the Game and all associated content
- You have a license to play and use the Game on your devices

MINECRAFT REALMS
When you use our Realms, you agree to our Terms and Conditions for Minecraft Realms

UPDATES
We might make upgrades, updates or patches (which we'll refer to as "updates") available from time to time
and sometimes we have to do that to continue providing the Game.

OWNERSHIP OF OUR GAME AND OTHER STUFF
Although we license you permission to install on your device and play our Game, we are still the owners of it.

CONTENT
If you make any content available on or through our Game, you must give us permission to use, copy, modify,
adapt, distribute, and publicly display that content. This permission must be irrevocable, and you must also
let us permit other people to use, copy, modify, adapt, distribute, and publicly display your content.

You agree that we may use your content in various ways, and you agree that we are not required to pay you for it.

If you're going to make something available on or through our Game, it must not:
- be offensive to people or otherwise unlawful
- infringe anyone else's rights
- contain anyone else's personal information
- trigger legal problems for us or other people

We reserve the right to take down any content.

These terms don't give us any ownership of the content you create - you're still the owner.

ACCOUNTS
To use the Game, you'll need to have a valid account ("Account").

You can't use anyone else's Account without permission.

You are responsible for:
- all activities that occur under your Account
- keeping your password confidential

TERMINATION
If we want to, we can terminate or suspend your access to the Game at any time.

If we do that, you will no longer have any of the rights to the Game given in this Agreement.

If you have bought the Game:
- subject to applicable law, you won't get any refund
- but if there's a good reason for it, we will try to give you advance notice by the email address
  linked to your Account

DISCLAIMER
To the fullest extent permitted by applicable law, we provide the Game "as-is" without warranties of any kind.

LIMITATION OF LIABILITY
To the fullest extent permitted by applicable law, we (this includes our affiliates and employees) are not liable
for any direct, indirect, incidental, punitive, special or consequential damages arising out of or in any way
connected with your use of the Game.

Your use of the Game is at your own risk.

The above does not affect any mandatory legal rights that we or you have under applicable law.

This Agreement, and your relationship with us under this Agreement, will be governed by the laws of the
State of Washington, U.S.A. excluding Washington's conflicts of laws rules.

If you have an issue, please contact our customer support:
https://help.minecraft.net

By using Minecraft, you agree to this EULA.
For the full and legally binding EULA, visit: {eula_url}
""".strip()


# ──────────────────────────────────────────────
#  Result Objects
# ──────────────────────────────────────────────

@dataclass
class EulaResult:
    """Result object for EULA operations."""
    success: bool
    message: str
    error: Optional[str] = None
    details: dict = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str, **details) -> "EulaResult":
        """Create a successful result."""
        return cls(success=True, message=message, details=details)

    @classmethod
    def fail(cls, message: str, error: Optional[str] = None, **details) -> "EulaResult":
        """Create a failed result."""
        return cls(success=False, message=message, error=error, details=details)


# ──────────────────────────────────────────────
#  EULA Manager
# ──────────────────────────────────────────────

class EulaManager:
    """
    Comprehensive Minecraft EULA manager.

    Args:
        server_dir:  Path to the Minecraft server directory
        config_path: Path to the application's config.json
    """

    def __init__(self, server_dir: str | Path, config_path: str | Path) -> None:
        self.server_dir = Path(server_dir)
        self.config_path = Path(config_path)
        self.eula_path = self.server_dir / "eula.txt"

    # ── 1. Check EULA Status ────────────────────

    def check_eula_status(self) -> bool:
        """
        Check if eula.txt exists and eula=true.

        Returns:
            True if EULA is accepted, False otherwise
        """
        if not self.eula_path.exists():
            logger.debug("eula.txt not found at %s", self.eula_path)
            return False

        try:
            content = self.eula_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip().lower()
                if stripped.startswith("eula="):
                    value = stripped.split("=", 1)[1].strip()
                    is_accepted = value == "true"
                    logger.debug("EULA status: %s (eula=%s)", is_accepted, value)
                    return is_accepted

            logger.warning("eula.txt found but no 'eula=' line detected")
            return False

        except OSError as exc:
            logger.error("Failed to read eula.txt: %s", exc)
            return False
        except Exception as exc:
            logger.error("Unexpected error reading eula.txt: %s", exc)
            return False

    # ── 2. Get EULA Content ─────────────────────

    def get_eula_content(self) -> str:
        """
        Return full content of eula.txt for display.

        Returns:
            eula.txt content as string, or error message if file not found
        """
        if not self.eula_path.exists():
            return f"# eula.txt not found at {self.eula_path}"

        try:
            content = self.eula_path.read_text(encoding="utf-8")
            logger.debug("Read %d bytes from eula.txt", len(content))
            return content
        except OSError as exc:
            error_msg = f"# Error reading eula.txt: {exc}"
            logger.error(error_msg)
            return error_msg
        except Exception as exc:
            error_msg = f"# Unexpected error: {exc}"
            logger.error(error_msg)
            return error_msg

    # ── 3. Auto-Accept EULA ─────────────────────

    def auto_accept_eula(self) -> EulaResult:
        """
        Automatically accept the EULA.

        Creates eula.txt with eula=true and Minecraft legal notice.

        Returns:
            EulaResult with success/failure details
        """
        try:
            # Ensure server directory exists
            self.server_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Ensured server directory exists: %s", self.server_dir)

        except OSError as exc:
            return EulaResult.fail(
                "Failed to create server directory",
                error=str(exc),
                path=str(self.server_dir),
            )

        try:
            # Generate timestamp
            timestamp = datetime.now(tz=timezone.utc).strftime("%a %b %d %H:%M:%S %Z %Y")

            # Write eula.txt
            content = EULA_TEMPLATE.format(
                url=EULA_URL,
                timestamp=timestamp,
                value="true",
            )

            self.eula_path.write_text(content, encoding="utf-8")
            logger.info("EULA accepted – wrote %s", self.eula_path)

            # Sync to config.json
            self._update_config(accepted=True)

            return EulaResult.ok(
                "EULA accepted successfully",
                path=str(self.eula_path),
                timestamp=timestamp,
                eula_url=EULA_URL,
            )

        except OSError as exc:
            return EulaResult.fail(
                "Failed to write eula.txt",
                error=str(exc),
                path=str(self.eula_path),
            )
        except Exception as exc:
            return EulaResult.fail(
                "Unexpected error during EULA acceptance",
                error=str(exc),
            )

    # ── 4. Prompt Accept EULA ───────────────────

    def prompt_accept_eula(self) -> bool:
        """
        Show user EULA text and ask for confirmation.

        If agreed: calls auto_accept_eula()
        If declined: returns False

        Returns:
            True if user accepted and EULA written successfully, False otherwise
        """
        print("\n" + "=" * 80)
        print("MINECRAFT END USER LICENSE AGREEMENT")
        print("=" * 80)
        print(MINECRAFT_EULA_TEXT.format(eula_url=EULA_URL))
        print("=" * 80)
        print(f"\nFull legal EULA: {EULA_URL}")
        print("=" * 80 + "\n")

        try:
            response = input("Do you accept the Minecraft EULA? (yes/no): ").strip().lower()

            if response in ("yes", "y", "true", "accept", "agree"):
                logger.info("User accepted EULA via prompt")
                result = self.auto_accept_eula()

                if result.success:
                    print(f"✓ {result.message}")
                    return True
                else:
                    print(f"✗ {result.message}")
                    if result.error:
                        print(f"  Error: {result.error}")
                    return False

            else:
                logger.info("User declined EULA (response: %s)", response)
                print("\n✗ You must accept the Minecraft EULA to run the server.")
                return False

        except (EOFError, KeyboardInterrupt):
            logger.info("EULA prompt interrupted by user")
            print("\n\n✗ EULA acceptance cancelled.")
            return False
        except Exception as exc:
            logger.error("Error during EULA prompt: %s", exc)
            print(f"\n✗ Error: {exc}")
            return False

    # ── 5. Validate EULA ────────────────────────

    def validate_eula(self) -> bool:
        """
        Validate that eula.txt exists and contains eula=true.

        This is more strict than check_eula_status - it also logs warnings
        about malformed files.

        Returns:
            True if valid and accepted, False otherwise
        """
        if not self.eula_path.exists():
            logger.warning("Validation failed: eula.txt does not exist at %s", self.eula_path)
            return False

        try:
            content = self.eula_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            if not lines:
                logger.warning("Validation failed: eula.txt is empty")
                return False

            # Look for eula=true line
            found_eula_line = False
            is_true = False

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue  # Comment line

                if "eula=" in stripped.lower():
                    found_eula_line = True
                    # Extract value
                    if "=" in stripped:
                        key, _, value = stripped.partition("=")
                        value = value.strip().lower()
                        is_true = value == "true"
                        logger.debug("Found eula line: %s (value: %s)", stripped, value)
                    break

            if not found_eula_line:
                logger.warning("Validation failed: no 'eula=' line found in eula.txt")
                return False

            if not is_true:
                logger.warning("Validation failed: eula=false in eula.txt")
                return False

            logger.info("EULA validation successful: eula=true")
            return True

        except OSError as exc:
            logger.error("Validation failed: cannot read eula.txt: %s", exc)
            return False
        except Exception as exc:
            logger.error("Validation failed: unexpected error: %s", exc)
            return False

    # ── 6. Get EULA Text ────────────────────────

    def get_eula_text(self) -> str:
        """
        Return the full Minecraft EULA legal text for display.

        Returns:
            Complete EULA text as a formatted string
        """
        return MINECRAFT_EULA_TEXT.format(eula_url=EULA_URL)

    # ── Additional Utility Methods ──────────────

    def is_accepted(self) -> bool:
        """
        Alias for check_eula_status() for backward compatibility.

        Returns:
            True if EULA is accepted
        """
        return self.check_eula_status()

    def accept(self) -> bool:
        """
        Accept the EULA (returns bool for backward compatibility).

        Returns:
            True on success, False on failure
        """
        result = self.auto_accept_eula()
        return result.success

    def decline(self) -> bool:
        """
        Decline / revoke EULA acceptance.

        Returns:
            True on success, False on failure
        """
        return self._write_eula(accepted=False)

    def get_eula_url(self) -> str:
        """Return the official Minecraft EULA URL."""
        return EULA_URL

    def get_status_summary(self) -> dict:
        """
        Return a detailed summary of the current EULA state.

        Returns:
            dict with keys: accepted, eula_path, eula_url, last_modified,
                          file_exists, file_size, is_valid
        """
        import os

        last_modified = None
        file_exists = self.eula_path.exists()
        file_size = 0
        is_valid = False

        if file_exists:
            try:
                stat = self.eula_path.stat()
                mtime = stat.st_mtime
                last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                file_size = stat.st_size
                is_valid = self.validate_eula()
            except OSError as exc:
                logger.warning("Could not stat eula.txt: %s", exc)

        return {
            "accepted": self.check_eula_status(),
            "eula_path": str(self.eula_path),
            "eula_url": EULA_URL,
            "last_modified": last_modified,
            "file_exists": file_exists,
            "file_size_bytes": file_size,
            "is_valid": is_valid,
        }

    # ── Private Helpers ─────────────────────────

    def _write_eula(self, accepted: bool) -> bool:
        """
        Write the eula.txt file (internal helper).

        Args:
            accepted: True to set eula=true, False to set eula=false

        Returns:
            True on success, False on failure
        """
        try:
            # Ensure the server directory exists
            self.server_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now(tz=timezone.utc).strftime("%a %b %d %H:%M:%S %Z %Y")
            content = EULA_TEMPLATE.format(
                url=EULA_URL,
                timestamp=timestamp,
                value="true" if accepted else "false",
            )

            self.eula_path.write_text(content, encoding="utf-8")
            logger.info("EULA %s – wrote %s", "accepted" if accepted else "declined", self.eula_path)

            # Sync to config.json
            self._update_config(accepted)

            return True

        except OSError as exc:
            logger.error("Failed to write eula.txt: %s", exc)
            return False
        except Exception as exc:
            logger.error("Unexpected error writing eula.txt: %s", exc)
            return False

    def _update_config(self, accepted: bool) -> None:
        """
        Update the eula_accepted flag in config.json.

        Args:
            accepted: True if EULA was accepted
        """
        try:
            if not self.config_path.exists():
                logger.debug("config.json does not exist at %s, skipping update", self.config_path)
                return

            with open(self.config_path, "r", encoding="utf-8") as fh:
                config = json.load(fh)

            config.setdefault("server", {})["eula_accepted"] = accepted

            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(config, fh, indent=2)

            logger.debug("Updated config.json eula_accepted=%s", accepted)

        except OSError as exc:
            logger.warning("Could not update config.json: %s", exc)
        except json.JSONDecodeError as exc:
            logger.warning("Could not parse config.json: %s", exc)
        except Exception as exc:
            logger.warning("Unexpected error updating config.json: %s", exc)
