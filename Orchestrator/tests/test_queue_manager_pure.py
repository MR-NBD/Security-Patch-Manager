"""
Test - Queue Manager (funzioni pure)

extract_advisory_base(), _matches_any(), KERNEL_PATTERNS, REBOOT_PATTERNS.
Nessun mock necessario.
"""

from app.services.queue_manager import (
    extract_advisory_base,
    _matches_any,
    KERNEL_PATTERNS,
    REBOOT_PATTERNS,
)


class TestExtractAdvisoryBase:
    """Testa extract_advisory_base() — estrae base USN senza revisione."""

    # --- Match validi ---

    def test_usn_with_revision_2(self):
        assert extract_advisory_base("USN-7412-2") == "USN-7412"

    def test_usn_with_revision_1(self):
        assert extract_advisory_base("USN-7412-1") == "USN-7412"

    def test_usn_with_high_revision(self):
        assert extract_advisory_base("USN-100-10") == "USN-100"

    def test_usn_large_number(self):
        assert extract_advisory_base("USN-99999-3") == "USN-99999"

    # --- Non-USN ritornano None ---

    def test_rhsa_returns_none(self):
        assert extract_advisory_base("RHSA-2024:1234") is None

    def test_rhba_returns_none(self):
        assert extract_advisory_base("RHBA-2024:5678") is None

    def test_cve_returns_none(self):
        assert extract_advisory_base("CVE-2024-1234") is None

    def test_empty_string_returns_none(self):
        assert extract_advisory_base("") is None

    # --- Edge cases ---

    def test_usn_without_revision_returns_none(self):
        """USN-7412 senza revisione non matcha il pattern."""
        assert extract_advisory_base("USN-7412") is None

    def test_usn_with_trailing_chars_returns_none(self):
        assert extract_advisory_base("USN-7412-2-extra") is None

    def test_usn_with_empty_suffix_returns_none(self):
        assert extract_advisory_base("USN-7412-") is None

    def test_lowercase_usn_returns_none(self):
        """Il regex è case-sensitive: usn- non matcha."""
        assert extract_advisory_base("usn-7412-2") is None

    def test_usn_with_non_numeric_revision_returns_none(self):
        assert extract_advisory_base("USN-7412-a") is None

    def test_usn_with_only_letters_returns_none(self):
        assert extract_advisory_base("USN-abc-1") is None


class TestMatchesAny:
    """Testa _matches_any() — substring match case-insensitive."""

    # --- KERNEL_PATTERNS ---

    def test_kernel_package_matches_kernel_patterns(self):
        assert _matches_any("kernel", KERNEL_PATTERNS) is True

    def test_linux_image_matches_kernel_patterns(self):
        assert _matches_any("linux-image-6.5.0-aws", KERNEL_PATTERNS) is True

    def test_linux_headers_matches_kernel_patterns(self):
        assert _matches_any("linux-headers-generic", KERNEL_PATTERNS) is True

    def test_linux_modules_matches_kernel_patterns(self):
        assert _matches_any("linux-modules-extra", KERNEL_PATTERNS) is True

    def test_linux_generic_matches_kernel_patterns(self):
        assert _matches_any("linux-generic-hwe-22.04", KERNEL_PATTERNS) is True

    def test_python_does_not_match_kernel_patterns(self):
        assert _matches_any("python3-requests", KERNEL_PATTERNS) is False

    def test_openssl_does_not_match_kernel_patterns(self):
        assert _matches_any("openssl", KERNEL_PATTERNS) is False

    # --- REBOOT_PATTERNS (superset) ---

    def test_kernel_also_matches_reboot_patterns(self):
        assert _matches_any("linux-image-aws", REBOOT_PATTERNS) is True

    def test_glibc_matches_reboot_patterns(self):
        assert _matches_any("glibc", REBOOT_PATTERNS) is True

    def test_libc6_matches_reboot_patterns(self):
        assert _matches_any("libc6-dev", REBOOT_PATTERNS) is True

    def test_systemd_matches_reboot_patterns(self):
        assert _matches_any("systemd", REBOOT_PATTERNS) is True

    def test_openssh_server_matches_reboot_patterns(self):
        assert _matches_any("openssh-server", REBOOT_PATTERNS) is True

    def test_initramfs_matches_reboot_patterns(self):
        assert _matches_any("initramfs-tools", REBOOT_PATTERNS) is True

    def test_grub_matches_reboot_patterns(self):
        assert _matches_any("grub-common", REBOOT_PATTERNS) is True

    def test_python_does_not_match_reboot_patterns(self):
        assert _matches_any("python3-pip", REBOOT_PATTERNS) is False

    def test_curl_does_not_match_reboot_patterns(self):
        assert _matches_any("curl", REBOOT_PATTERNS) is False

    # --- Case insensitivity ---

    def test_uppercase_name_matches(self):
        assert _matches_any("LINUX-IMAGE-5.15", KERNEL_PATTERNS) is True

    def test_mixed_case_name_matches(self):
        assert _matches_any("Kernel-Module", KERNEL_PATTERNS) is True

    # --- Edge cases ---

    def test_none_name_returns_false(self):
        assert _matches_any(None, KERNEL_PATTERNS) is False

    def test_empty_name_returns_false(self):
        assert _matches_any("", KERNEL_PATTERNS) is False

    def test_substring_match_not_exact(self):
        """Verifica che sia substring match: 'linux-image-aws' matcha 'linux-image'."""
        assert _matches_any("linux-image-aws-hwe-6.2", KERNEL_PATTERNS) is True

    # --- KERNEL ⊆ REBOOT ---

    def test_glibc_in_reboot_not_kernel(self):
        assert _matches_any("glibc", REBOOT_PATTERNS) is True
        assert _matches_any("glibc", KERNEL_PATTERNS) is False


class TestPatternSets:
    """Testa integrità delle costanti pubbliche KERNEL_PATTERNS e REBOOT_PATTERNS."""

    def test_kernel_patterns_not_empty(self):
        assert len(KERNEL_PATTERNS) > 0

    def test_reboot_patterns_not_empty(self):
        assert len(REBOOT_PATTERNS) > 0

    def test_kernel_is_subset_of_reboot(self):
        """Tutti i pattern kernel implicano reboot."""
        for p in KERNEL_PATTERNS:
            assert p in REBOOT_PATTERNS, f"'{p}' in KERNEL_PATTERNS ma non in REBOOT_PATTERNS"

    def test_reboot_is_strict_superset_of_kernel(self):
        """REBOOT ha pattern aggiuntivi oltre ai kernel."""
        assert len(REBOOT_PATTERNS) > len(KERNEL_PATTERNS)

    def test_kernel_in_kernel_patterns(self):
        assert "kernel" in KERNEL_PATTERNS

    def test_linux_image_in_kernel_patterns(self):
        assert "linux-image" in KERNEL_PATTERNS

    def test_glibc_in_reboot_patterns(self):
        assert "glibc" in REBOOT_PATTERNS

    def test_systemd_in_reboot_patterns(self):
        assert "systemd" in REBOOT_PATTERNS

    def test_all_patterns_are_lowercase(self):
        """Pattern sono già lowercase — _matches_any fa .lower() sul nome."""
        for p in REBOOT_PATTERNS:
            assert p == p.lower(), f"Pattern '{p}' non è lowercase"
