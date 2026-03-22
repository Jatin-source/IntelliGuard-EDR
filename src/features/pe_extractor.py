import os
import math
import re
from collections import Counter
import lief
import pandas as pd
from src.utils.logger import logger

# Maximum bytes to read for string/entropy analysis (50 MB)
_MAX_READ_BYTES = 50 * 1024 * 1024


class PEFeatureExtractor:
    """Extracts PE features using LIEF, mapping them to Kaggle + EMBER column schemas."""

    # Suspicious strings to count (EMBER strings.string_counts.*)
    SUSPICIOUS_STRINGS = [
        'http://', 'https://', 'ftp', 'download', 'install', 'command', 'shell',
        'powershell', 'registry_key', 'password', 'crypt', 'encode', 'decode',
        'base64', 'hidden', 'remote', 'connect', 'process', 'debug', 'delete',
        'service', 'security', 'privilege', 'token', 'mutex', 'thread', 'memory',
        'keyboard', 'clipboard', 'desktop', 'cookie', 'useragent', 'html',
        'javascript', 'internet', 'cache', 'certificate', 'system', 'environment',
        'module', 'resource', 'window', 'exit', 'create', 'get', 'post', 'file',
        'directory', 'disk', 'snapshot', 'enum', 'hostname', 'url',
    ]

    def __init__(self, file_path):
        self.file_path = file_path

    def extract(self):
        """Extracts PE features and returns a single-row DataFrame."""
        if not os.path.exists(self.file_path):
            logger.error(f"File not found: {self.file_path}")
            return None

        try:
            binary = lief.parse(self.file_path)
            if binary is None:
                return None

            # ── Read raw bytes ONCE (capped at 50 MB) ─────────────────
            file_size = os.path.getsize(self.file_path)
            try:
                with open(self.file_path, 'rb') as f:
                    raw_bytes = f.read(_MAX_READ_BYTES)
            except Exception:
                raw_bytes = b''

            features = {}

            # ==========================================
            # 1. KAGGLE EXPERT MAPPING (Strict Lowercase)
            # ==========================================
            self._extract_kaggle_features(binary, features)

            # ==========================================
            # 2. EMBER EXPERT MAPPING (EMBER-style names)
            # ==========================================
            self._extract_ember_headers(binary, features)
            self._extract_ember_authenticode(binary, features)
            self._extract_ember_general(binary, features, raw_bytes, file_size)
            self._extract_ember_sections(binary, features, file_size)
            self._extract_ember_strings(features, raw_bytes)
            self._extract_ember_imports(binary, features)

            # ==========================================
            # 3. SIGNATURE METADATA (used by ensemble)
            # ==========================================
            self._extract_signature_metadata(binary, features)

            return pd.DataFrame([features])

        except Exception as e:
            logger.error(f"Error extracting features with LIEF: {e}")
            return None

    # -------------------------------------------------------
    # Kaggle Features (25 lowercase columns)
    # -------------------------------------------------------
    def _extract_kaggle_features(self, binary, features):
        oh = binary.optional_header
        hdr = binary.header

        features['machine'] = hdr.machine.value
        features['sizeofoptionalheader'] = hdr.sizeof_optional_header
        features['characteristics'] = hdr.characteristics
        features['imagebase'] = oh.imagebase
        features['dllcharacteristics'] = oh.dll_characteristics
        features['majoroperatingsystemversion'] = oh.major_operating_system_version
        features['sizeofcode'] = oh.sizeof_code
        features['sizeofinitializeddata'] = oh.sizeof_initialized_data
        features['sizeofuninitializeddata'] = oh.sizeof_uninitialized_data
        features['exportedfunctions'] = len(binary.exported_functions) if binary.has_exports else 0
        features['importedfunctions'] = sum(len(lib.entries) for lib in binary.imports) if binary.has_imports else 0
        features['subsystem'] = oh.subsystem.value
        features['baseofdata'] = getattr(oh, 'baseofdata', 0)
        features['baseofcode'] = getattr(oh, 'baseofcode', 0)
        features['majorlinkerversion'] = oh.major_linker_version
        features['minorlinkerversion'] = oh.minor_linker_version
        features['majorimageversion'] = oh.major_image_version
        features['minorimageversion'] = oh.minor_image_version
        features['addressofentrypoint'] = oh.addressof_entrypoint
        features['sizeofimage'] = oh.sizeof_image
        features['sizeofheaders'] = oh.sizeof_headers
        features['check_sum'] = oh.checksum
        features['numberofsections'] = len(binary.sections)
        features['sectioncount'] = len(binary.sections)
        features['hasexporttable'] = 1 if binary.has_exports else 0
        features['overlaysize'] = len(binary.overlay) if binary.overlay else 0

        # Section-based Kaggle features
        sections = list(binary.sections)
        features['textsectionsize'] = sum(s.size for s in sections if s.name.strip('\x00').lower() == '.text')
        features['datasectionsize'] = sum(s.size for s in sections if s.name.strip('\x00').lower() == '.data')

        standard = {'.text', '.data', '.rdata', '.idata', '.edata', '.pdata', '.bss', '.rsrc', '.reloc', '.tls'}
        features['suspicioussectionnames'] = sum(1 for s in sections if s.name.strip('\x00').lower() not in standard)

        features['sectionsnb'] = len(sections)
        entropies = [s.entropy for s in sections if s.size > 0]
        features['minsectionentropy'] = min(entropies) if entropies else 0.0
        features['maxsectionentropy'] = max(entropies) if entropies else 0.0
        features['avgsectionentropy'] = (sum(entropies) / len(entropies)) if entropies else 0.0
        features['importeddlls'] = len(binary.imports)

    # -------------------------------------------------------
    # EMBER: COFF + DOS + Optional Headers
    # -------------------------------------------------------
    def _extract_ember_headers(self, binary, features):
        hdr = binary.header
        oh = binary.optional_header
        dos = binary.dos_header

        # COFF header
        features['header.coff.characteristics'] = hdr.characteristics
        features['header.coff.number_of_sections'] = hdr.numberof_sections
        features['header.coff.number_of_symbols'] = hdr.numberof_symbols
        features['header.coff.pointer_to_symbol_table'] = hdr.pointerto_symbol_table
        features['header.coff.sizeof_optional_header'] = hdr.sizeof_optional_header
        features['header.coff.timestamp'] = hdr.time_date_stamps

        # DOS header (all 15 e_* fields)
        features['header.dos.e_magic'] = dos.magic
        features['header.dos.e_cblp'] = dos.used_bytes_in_last_page
        features['header.dos.e_cp'] = dos.file_size_in_pages
        features['header.dos.e_crlc'] = dos.numberof_relocation
        features['header.dos.e_cparhdr'] = dos.header_size_in_paragraphs
        features['header.dos.e_minalloc'] = dos.minimum_extra_paragraphs
        features['header.dos.e_maxalloc'] = dos.maximum_extra_paragraphs
        features['header.dos.e_ss'] = dos.initial_relative_ss
        features['header.dos.e_sp'] = dos.initial_sp
        features['header.dos.e_csum'] = dos.checksum
        features['header.dos.e_ip'] = dos.initial_ip
        features['header.dos.e_cs'] = dos.initial_relative_cs
        features['header.dos.e_lfarlc'] = dos.addressof_relocation_table
        features['header.dos.e_ovno'] = dos.overlay_number
        features['header.dos.e_oemid'] = dos.oem_id
        features['header.dos.e_oeminfo'] = dos.oem_info
        features['header.dos.e_lfanew'] = dos.addressof_new_exeheader

        # Optional header (EMBER-style names)
        features['header.optional.magic'] = oh.magic.value
        features['header.optional.major_linker_version'] = oh.major_linker_version
        features['header.optional.minor_linker_version'] = oh.minor_linker_version
        features['header.optional.sizeof_code'] = oh.sizeof_code
        features['header.optional.sizeof_initialized_data'] = oh.sizeof_initialized_data
        features['header.optional.sizeof_uninitialized_data'] = oh.sizeof_uninitialized_data
        features['header.optional.address_of_entrypoint'] = oh.addressof_entrypoint
        features['header.optional.base_of_code'] = oh.baseof_code
        features['header.optional.base_of_data'] = getattr(oh, 'baseof_data', 0)
        features['header.optional.image_base'] = oh.imagebase
        features['header.optional.section_alignment'] = oh.section_alignment
        features['header.optional.checksum'] = oh.checksum
        features['header.optional.sizeof_image'] = oh.sizeof_image
        features['header.optional.sizeof_headers'] = oh.sizeof_headers
        features['header.optional.sizeof_code'] = oh.sizeof_code
        features['header.optional.sizeof_heap_commit'] = oh.sizeof_heap_commit
        features['header.optional.sizeof_heap_reserve'] = oh.sizeof_heap_reserve
        features['header.optional.sizeof_stack_commit'] = oh.sizeof_stack_commit
        features['header.optional.sizeof_stack_reserve'] = oh.sizeof_stack_reserve
        features['header.optional.dll_characteristics'] = oh.dll_characteristics
        features['header.optional.major_image_version'] = oh.major_image_version
        features['header.optional.minor_image_version'] = oh.minor_image_version
        features['header.optional.major_operating_system_version'] = oh.major_operating_system_version
        features['header.optional.minor_operating_system_version'] = oh.minor_operating_system_version
        features['header.optional.major_subsystem_version'] = oh.major_subsystem_version
        features['header.optional.minor_subsystem_version'] = oh.minor_subsystem_version
        features['header.optional.number_of_rvas_and_sizes'] = oh.numberof_rva_and_size

    # -------------------------------------------------------
    # EMBER: Authenticode / Digital Signature
    # -------------------------------------------------------
    def _extract_ember_authenticode(self, binary, features):
        sigs = list(binary.signatures) if hasattr(binary, 'signatures') else []
        has_sig = len(sigs) > 0

        if has_sig:
            sig = sigs[0]
            signers = list(sig.signers)
            certs = list(sig.certificates) if hasattr(sig, 'certificates') else []

            features['authenticode.num_certs'] = len(certs)
            features['authenticode.chain_max_depth'] = len(certs)
            features['authenticode.parse_error'] = 0
            features['authenticode.empty_program_name'] = 0

            # Check if self-signed
            if signers:
                si = signers[0]
                cert = si.cert
                is_self_signed = 1 if (cert.subject == cert.issuer) else 0
                features['authenticode.self_signed'] = is_self_signed
            else:
                features['authenticode.self_signed'] = 0

            # Signing time
            features['authenticode.latest_signing_time'] = 1  # has signing time
            features['authenticode.signing_time_diff'] = 0
            features['authenticode.no_countersigner'] = 0
        else:
            features['authenticode.num_certs'] = 0
            features['authenticode.chain_max_depth'] = 0
            features['authenticode.parse_error'] = 0
            features['authenticode.empty_program_name'] = 1
            features['authenticode.self_signed'] = 0
            features['authenticode.latest_signing_time'] = 0
            features['authenticode.signing_time_diff'] = 0
            features['authenticode.no_countersigner'] = 1

    # -------------------------------------------------------
    # EMBER: General file properties  (uses shared raw_bytes)
    # -------------------------------------------------------
    def _extract_ember_general(self, binary, features, raw_bytes: bytes, file_size: int):
        features['general.size'] = file_size
        features['general.is_pe'] = 1

        # Compute overall file entropy from shared buffer
        if raw_bytes:
            counts = Counter(raw_bytes)
            length = len(raw_bytes)
            entropy = sum(-(count / length) * math.log2(count / length) for count in counts.values())
            features['general.entropy'] = entropy
        else:
            features['general.entropy'] = 0.0

        # Start bytes (first 2 bytes as integer — magic number)
        features['general.start_bytes'] = binary.dos_header.magic

    # -------------------------------------------------------
    # EMBER: Section & Overlay info
    # -------------------------------------------------------
    def _extract_ember_sections(self, binary, features, file_size: int):
        features['section.sections'] = len(binary.sections)

        overlay_data = binary.overlay if binary.overlay else b''
        overlay_size = len(overlay_data)
        features['section.overlay.size'] = overlay_size
        features['section.overlay.size_ratio'] = overlay_size / file_size if file_size > 0 else 0.0

        # Overlay entropy
        if overlay_data and overlay_size > 0:
            counts = Counter(overlay_data)
            entropy = sum(-(count / overlay_size) * math.log2(count / overlay_size) for count in counts.values())
            features['section.overlay.entropy'] = entropy
        else:
            features['section.overlay.entropy'] = 0.0

    # -------------------------------------------------------
    # EMBER: String-based features  (uses shared raw_bytes)
    # -------------------------------------------------------
    def _extract_ember_strings(self, features, raw_bytes: bytes):
        """Extract printable strings and count suspicious patterns."""
        try:
            # Fast extract ASCII printable strings (min length 4)
            strings_b = re.findall(b'[ -~]{4,}', raw_bytes)
            strings = [s.decode('ascii', errors='ignore') for s in strings_b]

            features['strings.numstrings'] = len(strings)
            features['strings.printables'] = sum(len(s) for s in strings)

            if strings:
                lengths = [len(s) for s in strings]
                features['strings.avlength'] = sum(lengths) / len(lengths)

                # String entropy
                all_chars = ''.join(strings)
                if all_chars:
                    counts = Counter(all_chars)
                    total = len(all_chars)
                    entropy = sum(-(count / total) * math.log2(count / total) for count in counts.values())
                    features['strings.entropy'] = entropy
                else:
                    features['strings.entropy'] = 0.0

                # Printable character distribution
                raw_len = len(raw_bytes) if raw_bytes else 1
                features['strings.printabledist'] = features['strings.printables'] / raw_len
            else:
                features['strings.avlength'] = 0.0
                features['strings.entropy'] = 0.0
                features['strings.printabledist'] = 0.0

            # Count suspicious string patterns
            all_text = '\n'.join(strings).lower()
            for pattern in self.SUSPICIOUS_STRINGS:
                col_name = f'strings.string_counts.{pattern}'
                features[col_name] = all_text.count(pattern.lower())

        except Exception:
            features['strings.numstrings'] = 0
            features['strings.printables'] = 0
            features['strings.avlength'] = 0.0
            features['strings.entropy'] = 0.0
            features['strings.printabledist'] = 0.0
            for pattern in self.SUSPICIOUS_STRINGS:
                features[f'strings.string_counts.{pattern}'] = 0

    # -------------------------------------------------------
    # EMBER: One-Hot DLL Import Flags
    # -------------------------------------------------------
    def _extract_ember_imports(self, binary, features):
        """One-hot encode imported DLLs and extract import stats."""
        if binary.has_imports:
            for lib in binary.imports:
                dll_lower = lib.name.lower()
                features[f'imports.{dll_lower}'] = 1.0
                features[f'imports.{lib.name}'] = 1.0

        features['ImportsNbDLL'] = len(binary.imports) if binary.has_imports else 0
        features['SectionsNb'] = len(binary.sections)

    # -------------------------------------------------------
    # Signature Metadata (used by ensemble trust scoring)
    # -------------------------------------------------------
    def _extract_signature_metadata(self, binary, features):
        """Extract signature validity for ensemble-level trust scoring."""
        try:
            verify_result = binary.verify_signature()
            is_signed = str(verify_result) == 'VERIFICATION_FLAGS.OK'
            features['_meta.is_validly_signed'] = 1 if is_signed else 0

            sigs = list(binary.signatures) if hasattr(binary, 'signatures') else []
            if sigs and is_signed:
                signers = list(sigs[0].signers)
                if signers:
                    features['_meta.signer_subject'] = str(signers[0].cert.subject)
                else:
                    features['_meta.signer_subject'] = ''
            else:
                features['_meta.signer_subject'] = ''
        except Exception:
            features['_meta.is_validly_signed'] = 0
            features['_meta.signer_subject'] = ''